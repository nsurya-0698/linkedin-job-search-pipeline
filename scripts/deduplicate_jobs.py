#!/usr/bin/env python3
"""Detect duplicate job listings and assign deterministic canonical records."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from _common import (
    JOBS_FIELDS,
    PipelineError,
    atomic_write_csv,
    atomic_write_json,
    boolish,
    csv_path,
    extract_linkedin_job_id,
    file_lock,
    normalize_text,
    normalize_url,
    parse_iso_date,
    parse_json_list,
    print_json,
    read_csv_checked,
    resolve_workspace,
)


class UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self.parent[right_root] = left_root
        else:
            self.parent[left_root] = right_root


def jd_similarity(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    return difflib.SequenceMatcher(None, left_normalized, right_normalized, autojunk=False).ratio()


def _canonical_key(row: dict[str, str]) -> tuple[Any, ...]:
    active = boolish(row["job_active"]) is True
    verified = parse_iso_date(row["last_verified"])
    first_seen = parse_iso_date(row["first_seen"])
    # Prefer verified/active records, then the most recently verified, then oldest source record.
    return (
        0 if active else 1,
        -(verified.toordinal() if verified else 0),
        first_seen.toordinal() if first_seen else 9999999,
        row["job_id"],
    )


def _signals(left: dict[str, str], right: dict[str, str], threshold: float) -> list[str]:
    signals: list[str] = []
    left_req = normalize_text(left["requisition_id"])
    right_req = normalize_text(right["requisition_id"])
    if left_req and right_req and left_req != right_req:
        # Explicit, conflicting requisitions are negative evidence. Do not let a reused
        # title, location, URL, or templated JD collapse distinct openings.
        return signals
    left_linkedin = left["linkedin_job_id"] or extract_linkedin_job_id(left["url"])
    right_linkedin = right["linkedin_job_id"] or extract_linkedin_job_id(right["url"])
    if left_linkedin and left_linkedin == right_linkedin:
        signals.append("linkedin_job_id")

    left_url = normalize_url(left["url"])
    right_url = normalize_url(right["url"])
    if left_url and left_url == right_url:
        signals.append("canonical_url")

    company_same = normalize_text(left["company"]) == normalize_text(right["company"])
    title_same = normalize_text(left["role_title"]) == normalize_text(right["role_title"])
    location_left = normalize_text(left["location"])
    location_right = normalize_text(right["location"])
    location_same = bool(location_left and location_left == location_right)
    if company_same and title_same and location_same:
        signals.append("company_title_location")

    if company_same and left_req and left_req == right_req:
        signals.append("company_requisition_id")

    similarity = jd_similarity(left["job_description"], right["job_description"])
    if company_same and similarity >= threshold:
        signals.append(f"company_jd_similarity:{similarity:.3f}")
    if company_same and title_same and similarity >= min(0.85, threshold):
        signals.append(f"company_title_jd_similarity:{similarity:.3f}")
    return signals


def deduplicate(
    rows: Sequence[dict[str, str]], similarity_threshold: float
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not 0.5 <= similarity_threshold <= 1.0:
        raise PipelineError("similarity threshold must be between 0.5 and 1.0")
    ids = [row["job_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise PipelineError("jobs.csv contains duplicate job_id values; IDs must be unique")
    union = UnionFind(ids)
    pair_signals: dict[tuple[str, str], list[str]] = {}
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            signals = _signals(left, right, similarity_threshold)
            if signals:
                union.union(left["job_id"], right["job_id"])
                pair_signals[(left["job_id"], right["job_id"])] = signals

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[union.find(row["job_id"])].append(row)

    output = [dict(row) for row in rows]
    # Clean annotations written by pipeline versions that conflated duplicate screening
    # with application outcomes. Only exact tool-generated reasons are eligible.
    generated_duplicate_reason = re.compile(r"^duplicate of canonical job \S+$")
    for row in output:
        if (
            row["application_status"] == "SCREENED_OUT"
            and generated_duplicate_reason.match(row["rejection_reason"])
        ):
            row["application_status"] = "DISCOVERED"
            row["rejection_reason"] = ""
    by_id = {row["job_id"]: row for row in output}
    duplicate_groups: list[dict[str, Any]] = []
    for members in groups.values():
        canonical_source = min(members, key=_canonical_key)
        canonical_id = canonical_source["job_id"]
        sources = []
        alternate_urls: set[str] = set(parse_json_list(canonical_source["alternate_urls"]))
        for member in sorted(members, key=lambda item: item["job_id"]):
            sources.append(
                {
                    "job_id": member["job_id"],
                    "source": member["source"],
                    "url": member["url"],
                }
            )
            if member["url"] and member["url"] != canonical_source["url"]:
                alternate_urls.add(member["url"])
            target = by_id[member["job_id"]]
            target["canonical_job_id"] = canonical_id
            target["duplicate_of"] = "" if member["job_id"] == canonical_id else canonical_id

        canonical = by_id[canonical_id]
        canonical["duplicate_sources"] = json.dumps(
            sources, sort_keys=True, separators=(",", ":")
        )
        canonical["alternate_urls"] = json.dumps(sorted(alternate_urls), separators=(",", ":"))
        for member in members:
            if member["job_id"] != canonical_id:
                by_id[member["job_id"]]["duplicate_sources"] = ""

        if len(members) > 1:
            member_ids = sorted(member["job_id"] for member in members)
            relevant_signals = {
                f"{left}|{right}": signals
                for (left, right), signals in pair_signals.items()
                if left in member_ids and right in member_ids
            }
            duplicate_groups.append(
                {
                    "canonical_job_id": canonical_id,
                    "member_job_ids": member_ids,
                    "signals": relevant_signals,
                }
            )

    output.sort(key=lambda row: (row["canonical_job_id"], bool(row["duplicate_of"]), row["job_id"]))
    report = {
        "total_records": len(rows),
        "unique_jobs": len(groups),
        "duplicate_records": len(rows) - len(groups),
        "duplicate_groups": sorted(duplicate_groups, key=lambda item: item["canonical_job_id"]),
        "similarity_threshold": similarity_threshold,
    }
    return output, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect duplicate jobs using stable IDs, normalized URLs, requisitions, "
            "company/title/location, and JD similarity. The default is read-only."
        )
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.92,
        help="JD similarity threshold from 0.5 to 1.0 (default: 0.92)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Atomically annotate jobs.csv; preserves duplicate source rows as audit evidence",
    )
    parser.add_argument(
        "--canonical-output",
        type=Path,
        help="Write canonical records only to a new CSV; refuses to overwrite",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write the JSON duplicate report to a new file; refuses to overwrite",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        requested_outputs = [
            output.expanduser().resolve()
            for output in (args.canonical_output, args.report)
            if output is not None
        ]
        if len(requested_outputs) != len(set(requested_outputs)):
            raise PipelineError("--canonical-output and --report must use different paths")
        existing_outputs = [str(output) for output in requested_outputs if output.exists()]
        if existing_outputs:
            raise PipelineError(
                "Refusing to overwrite existing output(s): " + ", ".join(existing_outputs)
            )
        path = csv_path(workspace, "jobs.csv")
        rows = read_csv_checked(path, JOBS_FIELDS)
        annotated, report = deduplicate(rows, args.similarity_threshold)
        if args.apply:
            with file_lock(path):
                # Re-read under lock so a concurrent tracker update cannot be lost.
                current = read_csv_checked(path, JOBS_FIELDS)
                annotated, report = deduplicate(current, args.similarity_threshold)
                atomic_write_csv(path, JOBS_FIELDS, annotated)
        if args.canonical_output:
            canonical = [row for row in annotated if not row["duplicate_of"]]
            atomic_write_csv(
                args.canonical_output.expanduser().resolve(),
                JOBS_FIELDS,
                canonical,
                overwrite=False,
            )
        if args.report:
            atomic_write_json(args.report.expanduser().resolve(), report, overwrite=False)
    except (PipelineError, OSError, UnicodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print_json(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
