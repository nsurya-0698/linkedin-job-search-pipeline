#!/usr/bin/env python3
"""Create and track a focused two-to-three-company campaign batch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _common import PipelineError, atomic_write_json, slugify, utc_now


PHASES = (
    "RESEARCH",
    "AWAITING_ROLE_APPROVAL",
    "RESUME_PREPARATION",
    "AWAITING_RESUME_APPROVAL",
    "APPLICATION_PREPARATION",
    "AWAITING_SUBMISSION_APPROVAL",
    "APPLICATION_EXECUTION",
    "OUTREACH_PREPARATION",
    "AWAITING_OUTREACH_APPROVAL",
    "OUTREACH_EXECUTION",
    "COMPLETE",
)

CHECKPOINTS = ("ROLES", "RESUMES", "SUBMISSIONS", "OUTREACH")


def workspace_root(value: Path) -> Path:
    root = value.expanduser().resolve()
    if not (root / "campaign.json").is_file():
        raise PipelineError(f"Not an initialized campaign workspace: {root}")
    if not (root / "data" / "candidate-profile.md").is_file():
        raise PipelineError(f"Workspace is missing data/candidate-profile.md: {root}")
    return root


def campaigns_root(workspace: Path) -> Path:
    return workspace / "data" / "target-campaigns"


def load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise PipelineError(f"Campaign batch does not exist: {path.parent.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Invalid campaign manifest: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PipelineError(f"Unsupported campaign manifest: {path}")
    return value


def normalize_companies(values: list[str]) -> list[str]:
    companies: list[str] = []
    seen: set[str] = set()
    for raw in values:
        company = " ".join(raw.split())
        key = company.casefold()
        if not company or key in seen:
            continue
        seen.add(key)
        companies.append(company)
    if not 2 <= len(companies) <= 3:
        raise PipelineError("A target-company batch must contain exactly 2 or 3 unique companies")
    return companies


def create_batch(args: argparse.Namespace) -> dict[str, object]:
    workspace = workspace_root(args.workspace)
    companies = normalize_companies(args.company)
    batch_id = args.batch_id or f"{date.today().isoformat()}-{'-'.join(slugify(x) for x in companies)}"
    batch_id = slugify(batch_id, "target-campaign")
    directory = campaigns_root(workspace) / batch_id
    if directory.exists():
        raise PipelineError(f"Refusing to overwrite campaign batch: {directory}")
    for child in ("research", "decisions", "resumes", "applications", "outreach", "reports"):
        (directory / child).mkdir(parents=True, exist_ok=False)
    now = utc_now()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "batch_id": batch_id,
        "created_at": now,
        "updated_at": now,
        "workspace": str(workspace),
        "companies": companies,
        "phase": "RESEARCH",
        "approvals": [],
        "events": [{"at": now, "event": "BATCH_CREATED", "phase": "RESEARCH"}],
    }
    atomic_write_json(directory / "campaign.json", manifest, overwrite=False)
    return manifest


def set_phase(args: argparse.Namespace) -> dict[str, object]:
    workspace = workspace_root(args.workspace)
    path = campaigns_root(workspace) / args.batch_id / "campaign.json"
    manifest = load_manifest(path)
    current = str(manifest.get("phase", ""))
    if current not in PHASES:
        raise PipelineError(f"Manifest has invalid phase: {current}")
    requested = args.phase
    if requested != "BLOCKED":
        expected_index = PHASES.index(current) + 1
        if expected_index >= len(PHASES) or PHASES[expected_index] != requested:
            expected = PHASES[expected_index] if expected_index < len(PHASES) else "none"
            raise PipelineError(
                f"Invalid phase transition {current} -> {requested}; expected {expected}"
            )
    now = utc_now()
    manifest["phase"] = requested
    manifest["updated_at"] = now
    events = list(manifest.get("events", []))
    events.append({"at": now, "event": "PHASE_CHANGED", "from": current, "to": requested, "note": args.note or ""})
    manifest["events"] = events
    atomic_write_json(path, manifest)
    return manifest


def approve_checkpoint(args: argparse.Namespace) -> dict[str, object]:
    workspace = workspace_root(args.workspace)
    path = campaigns_root(workspace) / args.batch_id / "campaign.json"
    manifest = load_manifest(path)
    expected_phase = {
        "ROLES": "AWAITING_ROLE_APPROVAL",
        "RESUMES": "AWAITING_RESUME_APPROVAL",
        "SUBMISSIONS": "AWAITING_SUBMISSION_APPROVAL",
        "OUTREACH": "AWAITING_OUTREACH_APPROVAL",
    }[args.checkpoint]
    if manifest.get("phase") != expected_phase:
        raise PipelineError(
            f"{args.checkpoint} approval requires phase {expected_phase}, found {manifest.get('phase')}"
        )
    now = utc_now()
    approvals = list(manifest.get("approvals", []))
    approvals.append(
        {
            "at": now,
            "checkpoint": args.checkpoint,
            "scope": args.scope.strip(),
            "approved_by": "USER",
        }
    )
    manifest["approvals"] = approvals
    manifest["updated_at"] = now
    atomic_write_json(path, manifest)
    return manifest


def show_batch(args: argparse.Namespace) -> dict[str, object]:
    workspace = workspace_root(args.workspace)
    return load_manifest(campaigns_root(workspace) / args.batch_id / "campaign.json")


def list_batches(args: argparse.Namespace) -> list[dict[str, object]]:
    workspace = workspace_root(args.workspace)
    root = campaigns_root(workspace)
    if not root.exists():
        return []
    results = []
    for path in sorted(root.glob("*/campaign.json")):
        manifest = load_manifest(path)
        results.append(
            {
                "batch_id": manifest.get("batch_id"),
                "companies": manifest.get("companies"),
                "phase": manifest.get("phase"),
                "updated_at": manifest.get("updated_at"),
            }
        )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new 2-3 company campaign batch")
    create.add_argument("--workspace", type=Path, required=True)
    create.add_argument("--company", action="append", required=True)
    create.add_argument("--batch-id")
    create.set_defaults(handler=create_batch)

    phase = subparsers.add_parser("set-phase", help="Advance one lifecycle phase")
    phase.add_argument("--workspace", type=Path, required=True)
    phase.add_argument("--batch-id", required=True)
    phase.add_argument("--phase", choices=(*PHASES, "BLOCKED"), required=True)
    phase.add_argument("--note")
    phase.set_defaults(handler=set_phase)

    approve = subparsers.add_parser("approve", help="Record an explicit user checkpoint approval")
    approve.add_argument("--workspace", type=Path, required=True)
    approve.add_argument("--batch-id", required=True)
    approve.add_argument("--checkpoint", choices=CHECKPOINTS, required=True)
    approve.add_argument("--scope", required=True, help="Exact roles, files, submissions, or messages approved")
    approve.set_defaults(handler=approve_checkpoint)

    show = subparsers.add_parser("show", help="Show one batch manifest")
    show.add_argument("--workspace", type=Path, required=True)
    show.add_argument("--batch-id", required=True)
    show.set_defaults(handler=show_batch)

    listing = subparsers.add_parser("list", help="List all batches in a workspace")
    listing.add_argument("--workspace", type=Path, required=True)
    listing.set_defaults(handler=list_batches)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
