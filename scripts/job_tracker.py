#!/usr/bin/env python3
"""Safely add, update, gate, and list local job/application tracker records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common import (
    APPLICATION_STATUSES,
    APPLICATION_TRANSITIONS,
    APPLICATIONS_FIELDS,
    GATE_STATUSES,
    JOBS_FIELDS,
    JOB_STATUSES,
    PRIORITIES,
    SPONSORSHIP_STATUSES,
    TRISTATE,
    PipelineError,
    atomic_write_csv,
    boolish,
    csv_path,
    empty_row,
    ensure_unique,
    extract_linkedin_job_id,
    file_lock,
    normalize_text,
    normalize_url,
    number,
    parse_iso_date,
    print_json,
    priority_for_score,
    read_csv_checked,
    require_choice,
    resolve_workspace,
    slugify,
    today_iso,
    utc_now,
    validate_iso_date,
    validate_score,
    validate_scoring_dimensions,
)


IMMUTABLE_JOB_FIELDS = {"job_id", "priority", "application_status"}
IMMUTABLE_APPLICATION_FIELDS = {"application_id", "job_id", "priority"}
WORK_MODELS = ("REMOTE", "HYBRID", "ON_SITE", "UNKNOWN")
POST_SUBMISSION_STATUSES = {
    "APPLIED",
    "RECRUITER_CONTACTED",
    "SCREEN",
    "TECHNICAL",
    "ONSITE",
    "FINAL",
    "OFFER",
    "EMPLOYER_REJECTED",
}
INTERVIEW_STAGE_RANK = {
    "": 0,
    "SCREEN": 1,
    "TECHNICAL": 2,
    "ONSITE": 3,
    "FINAL": 4,
    "OFFER": 5,
}


def _read_description(args: argparse.Namespace) -> str:
    if getattr(args, "jd_file", None):
        return args.jd_file.expanduser().read_text(encoding="utf-8").strip()
    return (getattr(args, "description", "") or "").strip()


def _parse_assignments(assignments: Sequence[str], fields: Sequence[str]) -> dict[str, str]:
    allowed = set(fields)
    result: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise PipelineError(f"Expected FIELD=VALUE, received {assignment!r}")
        field, value = assignment.split("=", 1)
        field = field.strip()
        if field not in allowed:
            raise PipelineError(f"Unknown field {field!r}; valid fields: {', '.join(fields)}")
        result[field] = value.strip()
    return result


def _validate_job_updates(values: Mapping[str, str]) -> dict[str, str]:
    result = dict(values)
    if "job_status" in result:
        result["job_status"] = require_choice(result["job_status"], JOB_STATUSES, "job_status")
    if "job_active" in result:
        result["job_active"] = require_choice(result["job_active"], TRISTATE, "job_active")
    if "jd_changed" in result:
        result["jd_changed"] = require_choice(result["jd_changed"], TRISTATE, "jd_changed")
    if "hard_gate_status" in result:
        result["hard_gate_status"] = require_choice(
            result["hard_gate_status"], GATE_STATUSES, "hard_gate_status"
        )
    if "sponsorship_status" in result:
        result["sponsorship_status"] = require_choice(
            result["sponsorship_status"], SPONSORSHIP_STATUSES, "sponsorship_status"
        )
    if "application_status" in result and result["application_status"]:
        result["application_status"] = require_choice(
            result["application_status"], APPLICATION_STATUSES, "application_status"
        )
    if "work_model" in result:
        result["work_model"] = require_choice(result["work_model"], WORK_MODELS, "work_model")
    if "priority" in result:
        result["priority"] = require_choice(result["priority"], PRIORITIES, "priority")
    if "match_score" in result:
        result["match_score"] = validate_score(result["match_score"])
    if "priority_score" in result:
        result["priority_score"] = validate_score(result["priority_score"])
    if "scoring_dimensions" in result:
        result["scoring_dimensions"] = validate_scoring_dimensions(result["scoring_dimensions"])
    for field in ("first_seen", "last_verified", "application_deadline"):
        if field in result:
            result[field] = validate_iso_date(result[field], field)
    for field in ("experience_min_years", "experience_max_years"):
        if field in result and result[field]:
            parsed = number(result[field])
            if parsed is None or parsed < 0:
                raise PipelineError(f"{field} must be a non-negative number")
            result[field] = f"{parsed:g}"
    if "experience_min_years" in result and "experience_max_years" in result:
        lower = number(result["experience_min_years"])
        upper = number(result["experience_max_years"])
        if lower is not None and upper is not None and lower > upper:
            raise PipelineError("experience_min_years cannot exceed experience_max_years")
    if "url" in result:
        result["url"] = result["url"].strip()
    return result


def _validate_application_updates(values: Mapping[str, str]) -> dict[str, str]:
    result = dict(values)
    if "application_status" in result:
        result["application_status"] = require_choice(
            result["application_status"], APPLICATION_STATUSES, "application_status"
        )
    if "sponsorship_status" in result:
        result["sponsorship_status"] = require_choice(
            result["sponsorship_status"], SPONSORSHIP_STATUSES, "sponsorship_status"
        )
    if "priority" in result:
        result["priority"] = require_choice(result["priority"], PRIORITIES, "priority")
    if "match_score" in result:
        result["match_score"] = validate_score(result["match_score"])
    if "priority_score" in result:
        result["priority_score"] = validate_score(result["priority_score"])
    if "scoring_dimensions" in result:
        result["scoring_dimensions"] = validate_scoring_dimensions(result["scoring_dimensions"])
    if "interview_stage" in result:
        result["interview_stage"] = require_choice(
            result["interview_stage"], tuple(INTERVIEW_STAGE_RANK), "interview_stage"
        )
    for field in (
        "date_discovered",
        "date_verified",
        "date_prepared",
        "date_approved",
        "date_applied",
        "follow_up_date",
    ):
        if field in result:
            result[field] = validate_iso_date(result[field], field)
    return result


def _find(rows: Sequence[dict[str, str]], field: str, value: str) -> dict[str, str]:
    for row in rows:
        if row[field] == value:
            return row
    raise PipelineError(f"No record with {field}={value!r}")


def _duplicate_job(rows: Sequence[dict[str, str]], candidate: Mapping[str, str]) -> str | None:
    linkedin_id = candidate.get("linkedin_job_id", "")
    candidate_url = normalize_url(candidate.get("url", ""))
    company = normalize_text(candidate.get("company", ""))
    title = normalize_text(candidate.get("role_title", ""))
    location = normalize_text(candidate.get("location", ""))
    requisition = normalize_text(candidate.get("requisition_id", ""))
    for row in rows:
        row_requisition = normalize_text(row["requisition_id"])
        if requisition and row_requisition and requisition != row_requisition:
            continue
        if linkedin_id and row["linkedin_job_id"] == linkedin_id:
            return row["job_id"]
        if candidate_url and normalize_url(row["url"]) == candidate_url:
            return row["job_id"]
        if requisition and company and normalize_text(row["company"]) == company:
            if row_requisition == requisition:
                return row["job_id"]
        if company and title and location:
            if (
                normalize_text(row["company"]) == company
                and normalize_text(row["role_title"]) == title
                and normalize_text(row["location"]) == location
            ):
                return row["job_id"]
    return None


def add_job(workspace: Path, args: argparse.Namespace) -> dict[str, str]:
    path = csv_path(workspace, "jobs.csv")
    description = _read_description(args)
    first_seen = validate_iso_date(args.first_seen or today_iso(), "first_seen")
    last_verified = validate_iso_date(args.verified_on or "", "verified_on")
    linkedin_id = args.linkedin_job_id or extract_linkedin_job_id(args.url)
    match_score = validate_score(args.match_score)
    priority_score = validate_score(args.priority_score)
    priority = priority_for_score(number(priority_score))
    active = "TRUE" if last_verified else "UNKNOWN"
    status = "ACTIVE" if last_verified else "DISCOVERED"
    values = {
        "job_id": args.job_id.strip(),
        "canonical_job_id": args.job_id.strip(),
        "linkedin_job_id": linkedin_id,
        "requisition_id": args.requisition_id,
        "company": args.company,
        "role_title": args.title,
        "url": args.url,
        "source": args.source,
        "location": args.location,
        "work_model": require_choice(args.work_model, WORK_MODELS, "work_model"),
        "first_seen": first_seen,
        "last_verified": last_verified,
        "job_status": status,
        "job_active": active,
        "jd_changed": "UNKNOWN",
        "seniority": args.seniority,
        "job_description": description,
        "required_qualifications": args.required_qualifications,
        "preferred_qualifications": args.preferred_qualifications,
        "technologies": args.technologies,
        "responsibilities": args.responsibilities,
        "sponsorship_status": require_choice(
            args.sponsorship_status, SPONSORSHIP_STATUSES, "sponsorship_status"
        ),
        "sponsorship_evidence": args.sponsorship_evidence,
        "experience_min_years": args.experience_min_years,
        "experience_max_years": args.experience_max_years,
        "match_score": match_score,
        "priority_score": priority_score,
        "scoring_dimensions": validate_scoring_dimensions(args.scoring_dimensions),
        "score_rationale": args.score_rationale,
        "priority": priority,
        "hard_gate_status": "NOT_EVALUATED",
        "application_status": "DISCOVERED",
        "application_deadline": args.application_deadline,
        "jd_hash": hashlib.sha256(description.encode("utf-8")).hexdigest() if description else "",
        "notes": args.notes,
    }
    values = _validate_job_updates(values)
    if not values["job_id"]:
        raise PipelineError("job_id cannot be empty")
    if not values["company"] or not values["role_title"] or not values["url"]:
        raise PipelineError("company, title, and URL are required")

    row = empty_row(JOBS_FIELDS, values)
    with file_lock(path):
        rows = read_csv_checked(path, JOBS_FIELDS)
        ensure_unique(rows, "job_id", row["job_id"])
        duplicate = _duplicate_job(rows, row)
        if duplicate:
            raise PipelineError(
                f"Job matches existing record {duplicate}; run deduplicate_jobs.py for canonical analysis"
            )
        rows.append(row)
        atomic_write_csv(path, JOBS_FIELDS, rows)
    return row


def update_job(workspace: Path, job_id: str, assignments: Sequence[str]) -> dict[str, str]:
    path = csv_path(workspace, "jobs.csv")
    updates = _parse_assignments(assignments, JOBS_FIELDS)
    forbidden = IMMUTABLE_JOB_FIELDS.intersection(updates)
    if forbidden:
        raise PipelineError(f"Immutable field(s) cannot be updated: {', '.join(sorted(forbidden))}")
    updates = _validate_job_updates(updates)
    with file_lock(path):
        rows = read_csv_checked(path, JOBS_FIELDS)
        row = _find(rows, "job_id", job_id)
        old_description = row["job_description"]
        row.update(updates)
        if "priority_score" in updates:
            row["priority"] = priority_for_score(number(row["priority_score"]))
        if "job_description" in updates:
            row["jd_hash"] = (
                hashlib.sha256(row["job_description"].encode("utf-8")).hexdigest()
                if row["job_description"]
                else ""
            )
            if old_description and row["job_description"] != old_description:
                row["jd_changed"] = "TRUE"
                row["job_status"] = "MATERIALLY_CHANGED"
                row["hard_gate_status"] = "REVIEW_REQUIRED"
                row["gate_unknowns"] = json.dumps(
                    ["job description changed and must be re-scored"], separators=(",", ":")
                )
        # Revalidate the combined experience range.
        _validate_job_updates(
            {
                "experience_min_years": row["experience_min_years"],
                "experience_max_years": row["experience_max_years"],
            }
        )
        atomic_write_csv(path, JOBS_FIELDS, rows)
    return row


def evaluate_gate(workspace: Path, args: argparse.Namespace) -> dict[str, str]:
    path = csv_path(workspace, "jobs.csv")
    applications_path = csv_path(workspace, "applications.csv")
    candidate_sponsorship = args.candidate_requires_sponsorship.upper()
    if candidate_sponsorship not in {"YES", "NO", "UNKNOWN"}:
        raise PipelineError("candidate-requires-sponsorship must be YES, NO, or UNKNOWN")
    with file_lock(applications_path):
        with file_lock(path):
            applications = read_csv_checked(applications_path, APPLICATIONS_FIELDS)
            original_applications = [dict(item) for item in applications]
            rows = read_csv_checked(path, JOBS_FIELDS)
            row = _find(rows, "job_id", args.job_id)
            reasons: list[str] = []
            unknowns: list[str] = []
            review_blockers: list[str] = []

            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise PipelineError("as_of must be YYYY-MM-DD") from exc
            stale_cutoff = as_of - timedelta(days=args.freshness_days)

            active = boolish(row["job_active"])
            if active is False or row["job_status"] in {"CLOSED", "REMOVED", "EXPIRED"}:
                reasons.append("position is not active")
            elif active is None or not row["last_verified"]:
                unknowns.append("freshness")
                review_blockers.append("job has not been verified active")
            else:
                verified = parse_iso_date(row["last_verified"])
                if verified is not None and verified > as_of:
                    unknowns.append("freshness")
                    review_blockers.append("last verification date is in the future")
                elif verified is None or verified < stale_cutoff or row["job_status"] == "STALE":
                    unknowns.append("freshness")
                    review_blockers.append(
                        f"last verification is older than the {args.freshness_days}-day freshness window"
                    )

            if row["job_status"] == "MATERIALLY_CHANGED" or row["jd_changed"] == "TRUE":
                unknowns.append("material JD change")
                review_blockers.append("job description changed and must be re-scored")

            minimum = number(row["experience_min_years"])
            if minimum is not None and minimum > 5:
                reasons.append(f"explicit minimum experience {minimum:g} years exceeds 5-year limit")
            elif minimum is None:
                unknowns.append("experience requirement")

            sponsorship = row["sponsorship_status"]
            incompatible = sponsorship in {"INCOMPATIBLE", "NO_SPONSORSHIP"}
            if incompatible and candidate_sponsorship == "YES":
                reasons.append("explicit sponsorship/work-authorization incompatibility")
            elif incompatible and candidate_sponsorship == "UNKNOWN":
                unknowns.append("candidate sponsorship requirement")
            elif (
                sponsorship in {"UNKNOWN", "REQUIRES_CONFIRMATION"}
                and candidate_sponsorship != "NO"
            ):
                unknowns.append("sponsorship")
            if candidate_sponsorship == "UNKNOWN":
                unknowns.append("candidate sponsorship requirement")

            if args.core_mismatch:
                reasons.append("core required qualifications are clearly absent")
            if args.location_impossible:
                reasons.append("location requirement is impossible")
            if args.role_mismatch:
                reasons.append("role type is fundamentally outside candidate background")

            if reasons:
                status = "REJECT"
            elif review_blockers or "candidate sponsorship requirement" in unknowns:
                status = "REVIEW_REQUIRED"
            else:
                status = "PASS"

            row["hard_gate_status"] = status
            row["gate_evaluated_at"] = utc_now()
            row["gate_unknowns"] = json.dumps(
                sorted(set(unknowns + review_blockers)), separators=(",", ":")
            )
            row["rejection_reason"] = "; ".join(reasons)

            application = next(
                (item for item in applications if item["job_id"] == args.job_id), None
            )
            applications_changed = False
            if application is not None:
                submitted = bool(application["date_applied"]) or application[
                    "application_status"
                ] in POST_SUBMISSION_STATUSES
                if status == "REJECT" and not submitted:
                    screened_status = (
                        "CLOSED_OR_EXPIRED"
                        if "position is not active" in reasons
                        else "SCREENED_OUT"
                    )
                    if application["application_status"] != screened_status:
                        application["application_status"] = screened_status
                        applications_changed = True
                # Application state owns this snapshot once a record exists; submitted
                # outcomes are never rewritten by screening.
                row["application_status"] = application["application_status"]
            elif status == "REJECT":
                row["application_status"] = "SCREENED_OUT"
            elif row["application_status"] == "DISCOVERED":
                row["application_status"] = "EVALUATED"

            if applications_changed:
                atomic_write_csv(applications_path, APPLICATIONS_FIELDS, applications)
            try:
                atomic_write_csv(path, JOBS_FIELDS, rows)
            except Exception:
                if applications_changed:
                    atomic_write_csv(
                        applications_path, APPLICATIONS_FIELDS, original_applications
                    )
                raise
    return row


def add_application(workspace: Path, args: argparse.Namespace) -> dict[str, str]:
    jobs_path = csv_path(workspace, "jobs.csv")
    applications_path = csv_path(workspace, "applications.csv")
    with file_lock(applications_path):
        with file_lock(jobs_path):
            jobs = read_csv_checked(jobs_path, JOBS_FIELDS)
            job = _find(jobs, "job_id", args.job_id)
            if job["duplicate_of"]:
                raise PipelineError(
                    f"Cannot create an application for duplicate job {args.job_id}; use {job['canonical_job_id']}"
                )
            if job["hard_gate_status"] != "PASS":
                raise PipelineError(
                    f"Job hard gate is {job['hard_gate_status']}; only PASS jobs can become applications"
                )
            try:
                as_of = date.fromisoformat(args.as_of)
            except ValueError as exc:
                raise PipelineError("as_of must be YYYY-MM-DD") from exc
            verified = parse_iso_date(job["last_verified"])
            if (
                boolish(job["job_active"]) is not True
                or verified is None
                or verified > as_of
                or verified < as_of - timedelta(days=args.freshness_days)
                or job["job_status"] != "ACTIVE"
                or job["jd_changed"] == "TRUE"
            ):
                raise PipelineError(
                    "Job is not freshly verified and unchanged; re-verify and re-evaluate before preparation"
                )
            score = number(job["match_score"])
            if score is None or score < 50:
                raise PipelineError(
                    "Job requires a meaningful match_score of at least 50 before preparation"
                )
            priority_score = number(job["priority_score"])
            if priority_score is None or priority_score < 50:
                raise PipelineError(
                    "Job requires a weighted priority_score of at least 50 before preparation"
                )
            try:
                gate_unknowns = set(json.loads(job["gate_unknowns"] or "[]"))
            except json.JSONDecodeError as exc:
                raise PipelineError("Tracked job gate_unknowns is invalid JSON") from exc
            if "sponsorship" in gate_unknowns or "candidate sponsorship requirement" in gate_unknowns:
                raise PipelineError(
                    "Resolve decision-changing sponsorship uncertainty before application preparation"
                )
            application_id = args.application_id or f"app-{slugify(job['job_id'])}"
            values = {
                "application_id": application_id,
                "job_id": job["job_id"],
                "company": job["company"],
                "role_title": job["role_title"],
                "url": job["url"],
                "date_discovered": job["first_seen"],
                "date_verified": job["last_verified"],
                "sponsorship_status": job["sponsorship_status"],
                "match_score": job["match_score"],
                "priority_score": job["priority_score"],
                "scoring_dimensions": job["scoring_dimensions"],
                "score_rationale": job["score_rationale"],
                "priority": job["priority"],
                "resume_version": args.resume_version or job["resume_version"],
                "application_status": "READY",
                "date_prepared": args.date_prepared or today_iso(),
                "notes": args.notes,
            }
            row = empty_row(APPLICATIONS_FIELDS, _validate_application_updates(values))
            applications = read_csv_checked(applications_path, APPLICATIONS_FIELDS)
            ensure_unique(applications, "application_id", row["application_id"])
            if any(item["job_id"] == row["job_id"] for item in applications):
                raise PipelineError(f"An application already exists for job {row['job_id']}")
            applications.append(row)
            job["application_status"] = "READY"
            if row["resume_version"]:
                job["resume_version"] = row["resume_version"]
            atomic_write_csv(applications_path, APPLICATIONS_FIELDS, applications)
            try:
                atomic_write_csv(jobs_path, JOBS_FIELDS, jobs)
            except Exception:
                # Restore the in-memory pre-append snapshot while both locks are held.
                atomic_write_csv(applications_path, APPLICATIONS_FIELDS, applications[:-1])
                raise
    return row


def set_application_status(workspace: Path, args: argparse.Namespace) -> dict[str, str]:
    path = csv_path(workspace, "applications.csv")
    jobs_path = csv_path(workspace, "jobs.csv")
    new_status = require_choice(args.status, APPLICATION_STATUSES, "status")
    updates = _validate_application_updates(_parse_assignments(args.set or [], APPLICATIONS_FIELDS))
    forbidden = IMMUTABLE_APPLICATION_FIELDS.intersection(updates)
    if forbidden:
        raise PipelineError(f"Immutable field(s) cannot be updated: {', '.join(sorted(forbidden))}")
    with file_lock(path):
        with file_lock(jobs_path):
            rows = read_csv_checked(path, APPLICATIONS_FIELDS)
            original_rows = [dict(item) for item in rows]
            row = _find(rows, "application_id", args.application_id)
            old_status = row["application_status"]
            current_stage = row["interview_stage"]
            resume_is_changing = (
                "resume_version" in updates and updates["resume_version"] != row["resume_version"]
            )
            historical_submission = bool(row["date_applied"]) or old_status in POST_SUBMISSION_STATUSES
            if resume_is_changing and historical_submission:
                if not args.allow_resume_correction:
                    raise PipelineError(
                        "Submitted resume_version is historical attribution; use "
                        "--allow-resume-correction with --correction-note for a factual correction"
                    )
                if not args.correction_note.strip():
                    raise PipelineError(
                        "--correction-note is required when correcting a submitted resume_version"
                    )
            if not args.allow_nonlinear and new_status != old_status:
                valid = APPLICATION_TRANSITIONS.get(old_status, set())
                if new_status not in valid:
                    raise PipelineError(
                        f"Invalid application transition {old_status} -> {new_status}; "
                        "use --allow-nonlinear only for an intentional historical correction"
                    )
            row.update(updates)
            if "priority_score" in updates:
                row["priority"] = priority_for_score(number(row["priority_score"]))
            if resume_is_changing and historical_submission:
                correction = (
                    f"RESUME_VERSION_CORRECTION {today_iso()}: {args.correction_note.strip()}"
                )
                row["notes"] = f"{row['notes']} | {correction}".strip(" |")
            row["application_status"] = new_status
            status_stage = new_status if new_status in INTERVIEW_STAGE_RANK else ""
            requested_stage = max(
                (row["interview_stage"], status_stage),
                key=lambda stage: INTERVIEW_STAGE_RANK[stage],
            )
            if INTERVIEW_STAGE_RANK[requested_stage] < INTERVIEW_STAGE_RANK[current_stage]:
                raise PipelineError(
                    f"interview_stage is monotonic and cannot move from {current_stage} to {requested_stage}"
                )
            row["interview_stage"] = requested_stage
            automatic_dates = {
                "READY": "date_prepared",
                "AWAITING_APPROVAL": "date_prepared",
                "APPROVED": "date_approved",
                "APPLIED": "date_applied",
            }
            date_field = automatic_dates.get(new_status)
            if date_field and not row[date_field]:
                row[date_field] = today_iso()
            if new_status == "APPLIED" and not row["date_approved"]:
                raise PipelineError(
                    "Cannot record APPLIED without date_approved; set date_approved=YYYY-MM-DD"
                )
            jobs = read_csv_checked(jobs_path, JOBS_FIELDS)
            job = _find(jobs, "job_id", row["job_id"])
            job["application_status"] = new_status
            if row["resume_version"] and not historical_submission:
                job["resume_version"] = row["resume_version"]
            for score_field in (
                "match_score",
                "priority_score",
                "scoring_dimensions",
                "score_rationale",
                "priority",
            ):
                if score_field in updates or score_field == "priority" and "priority_score" in updates:
                    job[score_field] = row[score_field]
            atomic_write_csv(path, APPLICATIONS_FIELDS, rows)
            try:
                atomic_write_csv(jobs_path, JOBS_FIELDS, jobs)
            except Exception:
                atomic_write_csv(path, APPLICATIONS_FIELDS, original_rows)
                raise
    return row


def list_records(workspace: Path, kind: str, status: str | None) -> list[dict[str, str]]:
    if kind == "jobs":
        rows = read_csv_checked(csv_path(workspace, "jobs.csv"), JOBS_FIELDS)
        if status:
            normalized = status.upper()
            rows = [
                row
                for row in rows
                if row["job_status"] == normalized
                or row["hard_gate_status"] == normalized
                or row["application_status"] == normalized
            ]
        return rows
    rows = read_csv_checked(csv_path(workspace, "applications.csv"), APPLICATIONS_FIELDS)
    if status:
        rows = [row for row in rows if row["application_status"] == status.upper()]
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Maintain campaign job and application trackers with schema validation, "
            "duplicate prevention, atomic writes, and explicit hard-gate state."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add-job", help="Add a unique discovered job")
    add.add_argument("--workspace", required=True, type=Path)
    add.add_argument("--job-id", required=True)
    add.add_argument("--company", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--linkedin-job-id", default="")
    add.add_argument("--requisition-id", default="")
    add.add_argument("--source", default="")
    add.add_argument("--location", default="")
    add.add_argument("--work-model", default="UNKNOWN", choices=WORK_MODELS)
    add.add_argument("--first-seen", default="")
    add.add_argument("--verified-on", default="")
    add.add_argument("--seniority", default="")
    description_group = add.add_mutually_exclusive_group()
    description_group.add_argument("--description", default="")
    description_group.add_argument("--jd-file", type=Path)
    add.add_argument("--required-qualifications", default="")
    add.add_argument("--preferred-qualifications", default="")
    add.add_argument("--technologies", default="")
    add.add_argument("--responsibilities", default="")
    add.add_argument("--sponsorship-status", default="UNKNOWN", choices=SPONSORSHIP_STATUSES)
    add.add_argument("--sponsorship-evidence", default="")
    add.add_argument("--experience-min-years", default="")
    add.add_argument("--experience-max-years", default="")
    add.add_argument("--match-score", default="")
    add.add_argument(
        "--priority-score",
        default="",
        help="Weighted 0-100 opportunity score, distinct from JD relevance/match score",
    )
    add.add_argument(
        "--scoring-dimensions",
        default="",
        help='JSON object of scored dimensions, e.g. {"role_alignment":80,"remote_priority":100}',
    )
    add.add_argument("--score-rationale", default="")
    add.add_argument("--application-deadline", default="")
    add.add_argument("--notes", default="")

    update = subparsers.add_parser("update-job", help="Atomically update selected job fields")
    update.add_argument("--workspace", required=True, type=Path)
    update.add_argument("--job-id", required=True)
    update.add_argument(
        "--set",
        action="append",
        required=True,
        metavar="FIELD=VALUE",
        help="Repeat for each field; job_id is immutable",
    )

    gate = subparsers.add_parser(
        "evaluate-gate", help="Evaluate hard rejection before resume preparation"
    )
    gate.add_argument("--workspace", required=True, type=Path)
    gate.add_argument("--job-id", required=True)
    gate.add_argument(
        "--candidate-requires-sponsorship",
        required=True,
        choices=("YES", "NO", "UNKNOWN"),
    )
    gate.add_argument(
        "--as-of", default=date.today().isoformat(), help="Freshness evaluation date (YYYY-MM-DD)"
    )
    gate.add_argument(
        "--freshness-days",
        type=int,
        default=3,
        help="Maximum age of last verification before review is required (default: 3)",
    )
    gate.add_argument("--core-mismatch", action="store_true")
    gate.add_argument("--location-impossible", action="store_true")
    gate.add_argument("--role-mismatch", action="store_true")

    application = subparsers.add_parser(
        "add-application", help="Create one prepared application for an eligible canonical job"
    )
    application.add_argument("--workspace", required=True, type=Path)
    application.add_argument("--job-id", required=True)
    application.add_argument("--application-id", default="")
    application.add_argument("--resume-version", default="")
    application.add_argument("--date-prepared", default="")
    application.add_argument("--notes", default="")
    application.add_argument(
        "--as-of", default=date.today().isoformat(), help="Freshness evaluation date (YYYY-MM-DD)"
    )
    application.add_argument(
        "--freshness-days",
        type=int,
        default=3,
        help="Maximum verification age allowed for preparation (default: 3)",
    )

    status = subparsers.add_parser(
        "set-application-status", help="Record a validated application-state transition"
    )
    status.add_argument("--workspace", required=True, type=Path)
    status.add_argument("--application-id", required=True)
    status.add_argument("--status", required=True, choices=APPLICATION_STATUSES)
    status.add_argument("--set", action="append", metavar="FIELD=VALUE")
    status.add_argument(
        "--allow-nonlinear",
        action="store_true",
        help="Allow a deliberate historical correction outside the normal state machine",
    )
    status.add_argument(
        "--allow-resume-correction",
        action="store_true",
        help="Permit a factual correction to submitted resume attribution",
    )
    status.add_argument(
        "--correction-note",
        default="",
        help="Required audit explanation when --allow-resume-correction changes resume_version",
    )

    listing = subparsers.add_parser("list", help="Print tracker records as JSON")
    listing.add_argument("--workspace", required=True, type=Path)
    listing.add_argument("--kind", choices=("jobs", "applications"), default="jobs")
    listing.add_argument("--status", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {"evaluate-gate", "add-application"} and args.freshness_days < 0:
        parser.error("--freshness-days cannot be negative")
    try:
        workspace = resolve_workspace(args.workspace)
        if args.command == "add-job":
            result: Any = add_job(workspace, args)
        elif args.command == "update-job":
            result = update_job(workspace, args.job_id, args.set)
        elif args.command == "evaluate-gate":
            result = evaluate_gate(workspace, args)
        elif args.command == "add-application":
            result = add_application(workspace, args)
        elif args.command == "set-application-status":
            result = set_application_status(workspace, args)
        else:
            result = list_records(workspace, args.kind, args.status or None)
    except (PipelineError, OSError, UnicodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print_json(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
