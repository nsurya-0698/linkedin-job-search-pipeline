#!/usr/bin/env python3
"""Build deterministic campaign dashboards and funnel reports from local CSV state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from _common import (
    APPLICATIONS_FIELDS,
    COMPANIES_FIELDS,
    CONTACTS_FIELDS,
    INTERVIEW_PREPARATION_FIELDS,
    JOBS_FIELDS,
    RESUME_VERSIONS_FIELDS,
    PipelineError,
    atomic_write_text,
    boolish,
    contact_priority_tier,
    csv_path,
    number,
    parse_iso_date,
    read_csv_checked,
    resolve_workspace,
)


SUBMITTED_STATUSES = {
    "APPLIED",
    "RECRUITER_CONTACTED",
    "SCREEN",
    "TECHNICAL",
    "ONSITE",
    "FINAL",
    "OFFER",
    "EMPLOYER_REJECTED",
}
RECRUITER_RESPONSE_STATUSES = {
    "SCREEN",
    "TECHNICAL",
    "ONSITE",
    "FINAL",
    "OFFER",
}
SCREEN_STATUSES = {"SCREEN", "TECHNICAL", "ONSITE", "FINAL", "OFFER"}
TECHNICAL_STATUSES = {"TECHNICAL", "ONSITE", "FINAL", "OFFER"}
FINAL_STATUSES = {"FINAL", "OFFER"}


def _count(rows: Iterable[Mapping[str, str]], predicate: Any) -> int:
    return sum(1 for row in rows if predicate(row))


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator * 100, 1)


def _reached_stage(row: Mapping[str, str], stages: set[str]) -> bool:
    """Count the current state or a retained highest interview stage after a terminal outcome."""
    return row["application_status"].upper() in stages or row["interview_stage"].upper() in stages


def _submitted_by(row: Mapping[str, str], as_of: date) -> bool:
    applied = parse_iso_date(row["date_applied"])
    if applied is not None:
        return applied <= as_of
    # Backward-compatible fallback for legacy rows that predate durable date tracking.
    return row["application_status"] in SUBMITTED_STATUSES


def _milestone_by(
    row: Mapping[str, str], *, date_field: str, fallback_statuses: set[str], as_of: date
) -> bool:
    milestone = parse_iso_date(row[date_field])
    if milestone is not None:
        return milestone <= as_of
    return row["application_status"] in fallback_statuses


def _priority_rank(value: str) -> int:
    return {
        "TOP_PRIORITY": 5,
        "HIGH_PRIORITY": 4,
        "GOOD": 3,
        "BORDERLINE": 2,
        "DO_NOT_APPLY": 1,
    }.get(value, 0)


def _canonical_jobs(jobs: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    canonical = [row for row in jobs if not row["duplicate_of"]]
    return canonical


def _job_summary(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "company": row["company"],
        "role_title": row["role_title"],
        "location": row["location"],
        "work_model": row["work_model"],
        "match_score": number(row["match_score"]),
        "priority_score": number(row["priority_score"]),
        "scoring_dimensions": row["scoring_dimensions"],
        "priority": row["priority"],
        "hard_gate_status": row["hard_gate_status"],
        "last_verified": row["last_verified"],
        "sponsorship_status": row["sponsorship_status"],
        "application_status": row["application_status"],
        "url": row["url"],
    }


def _gate_unknowns(row: Mapping[str, str]) -> set[str]:
    try:
        value = json.loads(row.get("gate_unknowns", "") or "[]")
    except json.JSONDecodeError:
        return {"INVALID_GATE_UNKNOWNS"}
    return {str(item) for item in value} if isinstance(value, list) else {"INVALID_GATE_UNKNOWNS"}


def _fresh_active(row: Mapping[str, str], *, as_of: date, stale_days: int) -> bool:
    verified = parse_iso_date(row["last_verified"])
    return (
        row["job_status"] == "ACTIVE"
        and boolish(row["job_active"]) is True
        and row["jd_changed"] != "TRUE"
        and verified is not None
        and as_of - timedelta(days=stale_days) <= verified <= as_of
    )


def _application_summary(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        "application_id": row["application_id"],
        "job_id": row["job_id"],
        "company": row["company"],
        "role_title": row["role_title"],
        "status": row["application_status"],
        "match_score": number(row["match_score"]),
        "priority_score": number(row["priority_score"]),
        "priority": row["priority"],
        "follow_up_date": row["follow_up_date"],
    }


def _identify_bottleneck(metrics: Mapping[str, Mapping[str, int]]) -> dict[str, str]:
    jobs = metrics["job_funnel"]
    interviews = metrics["interview_funnel"]
    if jobs["jobs_discovered"] < 10:
        return {
            "stage": "DISCOVERY",
            "explanation": "Too few jobs have been captured to maintain a strong qualified queue.",
        }
    if jobs["unique_jobs"] and jobs["active_jobs"] < max(3, round(jobs["unique_jobs"] * 0.2)):
        return {
            "stage": "FRESHNESS",
            "explanation": "A low share of unique jobs is currently verified active.",
        }
    if jobs["active_jobs"] >= 10 and jobs["high_priority_jobs"] < 3:
        return {
            "stage": "TARGETING",
            "explanation": "The active queue is producing too few high-priority matches.",
        }
    if jobs["high_priority_jobs"] >= 3 and jobs["applications_prepared"] < 2:
        return {
            "stage": "PREPARATION",
            "explanation": "High-priority jobs are not moving into prepared applications.",
        }
    if jobs["applications_prepared"] >= 3 and jobs["applications_submitted"] < 2:
        return {
            "stage": "APPROVAL_OR_SUBMISSION",
            "explanation": "Prepared applications are not moving through approval and submission.",
        }
    if jobs["applications_submitted"] >= 5 and interviews["recruiter_responses"] == 0:
        return {
            "stage": "RECRUITER_RESPONSE",
            "explanation": "Qualified applications have not yet generated recruiter responses.",
        }
    if interviews["recruiter_screens"] >= 3 and interviews["technical_interviews"] == 0:
        return {
            "stage": "SCREEN_CONVERSION",
            "explanation": "Recruiter screens are not converting to technical interviews.",
        }
    if interviews["technical_interviews"] >= 3 and interviews["final_rounds"] == 0:
        return {
            "stage": "TECHNICAL_INTERVIEW",
            "explanation": "Technical interviews are not converting to final rounds.",
        }
    if interviews["final_rounds"] >= 2 and interviews["offers"] == 0:
        return {
            "stage": "FINAL_ROUND",
            "explanation": "Final rounds have not converted to offers.",
        }
    return {
        "stage": "INSUFFICIENT_SIGNAL",
        "explanation": "No statistically useful bottleneck is visible yet; continue collecting outcomes.",
    }


def build_report(workspace: Path, *, as_of: date, stale_days: int, top_n: int) -> dict[str, Any]:
    jobs = read_csv_checked(csv_path(workspace, "jobs.csv"), JOBS_FIELDS)
    contacts = read_csv_checked(csv_path(workspace, "contacts.csv"), CONTACTS_FIELDS)
    applications = read_csv_checked(csv_path(workspace, "applications.csv"), APPLICATIONS_FIELDS)
    companies = read_csv_checked(csv_path(workspace, "companies.csv"), COMPANIES_FIELDS)
    versions = read_csv_checked(
        csv_path(workspace, "resumes/resume_versions.csv"), RESUME_VERSIONS_FIELDS
    )
    interview_preparation = read_csv_checked(
        csv_path(workspace, "interview-preparation.csv"), INTERVIEW_PREPARATION_FIELDS
    )
    canonical = _canonical_jobs(jobs)

    hard_rejected = [row for row in canonical if row["hard_gate_status"] == "REJECT"]
    below_match = [
        row
        for row in canonical
        if number(row["match_score"]) is not None
        and number(row["match_score"]) < 50
        and row["hard_gate_status"] != "REJECT"
    ]
    submitted = [row for row in applications if _submitted_by(row, as_of)]
    recruiter_responses = [
        row
        for row in applications
        if _submitted_by(row, as_of) and _reached_stage(row, RECRUITER_RESPONSE_STATUSES)
    ]
    screens = [
        row
        for row in applications
        if _submitted_by(row, as_of) and _reached_stage(row, SCREEN_STATUSES)
    ]
    technical = [
        row
        for row in applications
        if _submitted_by(row, as_of) and _reached_stage(row, TECHNICAL_STATUSES)
    ]
    finals = [
        row
        for row in applications
        if _submitted_by(row, as_of) and _reached_stage(row, FINAL_STATUSES)
    ]
    offers = [
        row
        for row in applications
        if _submitted_by(row, as_of) and _reached_stage(row, {"OFFER"})
    ]

    job_funnel = {
        "jobs_discovered": len(jobs),
        "unique_jobs": len(canonical),
        "duplicate_records": len(jobs) - len(canonical),
        "active_jobs": _count(
            canonical,
            lambda row: boolish(row["job_active"]) is True and row["job_status"] == "ACTIVE",
        ),
        "rejected_by_sponsorship": _count(
            hard_rejected, lambda row: "sponsor" in row["rejection_reason"].lower()
        ),
        "rejected_by_experience": _count(
            hard_rejected, lambda row: "experience" in row["rejection_reason"].lower()
        ),
        "rejected_by_role_mismatch": _count(
            hard_rejected,
            lambda row: "role type" in row["rejection_reason"].lower()
            or "qualification" in row["rejection_reason"].lower(),
        ),
        "rejected_below_50_match": len(below_match),
        "high_priority_jobs": _count(
            canonical, lambda row: row["priority"] in {"TOP_PRIORITY", "HIGH_PRIORITY"}
        ),
        "applications_prepared": _count(
            applications,
            lambda row: _milestone_by(
                row,
                date_field="date_prepared",
                fallback_statuses={
                    "READY",
                    "AWAITING_APPROVAL",
                    "APPROVED",
                }.union(SUBMITTED_STATUSES),
                as_of=as_of,
            ),
        ),
        "applications_approved": _count(
            applications,
            lambda row: _milestone_by(
                row,
                date_field="date_approved",
                fallback_statuses={"APPROVED"}.union(SUBMITTED_STATUSES),
                as_of=as_of,
            ),
        ),
        "applications_submitted": len(submitted),
    }

    networking_funnel = {
        "contacts_discovered": len(contacts),
        "recruiters": _count(
            contacts,
            lambda row: contact_priority_tier(row) == "RECRUITER",
        ),
        "hiring_managers": _count(
            contacts,
            lambda row: contact_priority_tier(row) == "HIRING_MANAGER",
        ),
        "other_contacts": _count(
            contacts, lambda row: contact_priority_tier(row) == "OTHER"
        ),
        "engineering_leaders": _count(
            contacts,
            lambda row: row["relationship_type"].upper()
            in {"ENGINEERING_MANAGER", "DIRECTOR", "VP", "TECHNICAL_LEADER"},
        ),
        "connection_drafts": _count(
            contacts, lambda row: row["message_status"].upper() == "DRAFTED"
        ),
        "approved_messages": _count(
            contacts, lambda row: row["message_status"].upper() in {"APPROVED", "SENT"}
        ),
        "responses": _count(
            contacts,
            lambda row: row["response_status"].upper() not in {"", "NONE", "NO_RESPONSE"},
        ),
        "conversations": _count(
            contacts,
            lambda row: row["response_status"].upper() in {"CONVERSATION", "MEETING", "RESPONDED"},
        ),
        "referrals": _count(
            contacts, lambda row: row["referral_status"].upper() in {"REFERRED", "COMPLETED"}
        ),
    }

    interview_funnel = {
        "recruiter_responses": len(recruiter_responses),
        "recruiter_screens": len(screens),
        "technical_interviews": len(technical),
        "final_rounds": len(finals),
        "offers": len(offers),
        "employer_rejections": _count(
            applications,
            lambda row: row["application_status"] == "EMPLOYER_REJECTED"
            and _submitted_by(row, as_of),
        ),
    }

    metrics: dict[str, Mapping[str, int]] = {
        "job_funnel": job_funnel,
        "networking_funnel": networking_funnel,
        "interview_funnel": interview_funnel,
    }
    conversion_rates = {
        "deduplication_reduction_pct": _rate(job_funnel["duplicate_records"], job_funnel["jobs_discovered"]),
        "active_unique_jobs_pct": _rate(job_funnel["active_jobs"], job_funnel["unique_jobs"]),
        "prepared_per_high_priority_pct": _rate(
            job_funnel["applications_prepared"], job_funnel["high_priority_jobs"]
        ),
        "approved_per_prepared_pct": _rate(
            job_funnel["applications_approved"], job_funnel["applications_prepared"]
        ),
        "submitted_per_approved_pct": _rate(
            job_funnel["applications_submitted"], job_funnel["applications_approved"]
        ),
        "recruiter_response_per_submitted_pct": _rate(
            interview_funnel["recruiter_responses"], job_funnel["applications_submitted"]
        ),
        "screen_per_recruiter_response_pct": _rate(
            interview_funnel["recruiter_screens"], interview_funnel["recruiter_responses"]
        ),
        "technical_per_screen_pct": _rate(
            interview_funnel["technical_interviews"], interview_funnel["recruiter_screens"]
        ),
        "final_per_technical_pct": _rate(
            interview_funnel["final_rounds"], interview_funnel["technical_interviews"]
        ),
        "offer_per_final_pct": _rate(interview_funnel["offers"], interview_funnel["final_rounds"]),
        "network_response_pct": _rate(
            networking_funnel["responses"], networking_funnel["approved_messages"]
        ),
    }

    stale_cutoff = as_of - timedelta(days=stale_days)
    eligible_top = [
        row
        for row in canonical
        if _fresh_active(row, as_of=as_of, stale_days=stale_days)
        and row["hard_gate_status"] == "PASS"
        and (number(row["match_score"]) or 0) >= 50
        and (number(row["priority_score"]) or 0) >= 50
        and not {"sponsorship", "candidate sponsorship requirement"}.intersection(
            _gate_unknowns(row)
        )
    ]
    eligible_top.sort(
        key=lambda row: (
            -_priority_rank(row["priority"]),
            -(number(row["priority_score"]) or 0),
            -(number(row["match_score"]) or 0),
            0 if row["work_model"] == "REMOTE" else 1,
            row["company"].lower(),
            row["role_title"].lower(),
        )
    )

    stale = [
        row
        for row in canonical
        if row["job_status"] in {"DISCOVERED", "ACTIVE", "STALE"}
        and (parse_iso_date(row["last_verified"]) is None or parse_iso_date(row["last_verified"]) < stale_cutoff)
    ]
    sponsorship_unknown = [
        row
        for row in canonical
        if row["sponsorship_status"] in {"UNKNOWN", "REQUIRES_CONFIRMATION"}
        and row["hard_gate_status"] != "REJECT"
    ]
    awaiting = [
        row for row in applications if row["application_status"] == "AWAITING_APPROVAL"
    ]
    application_followups = [
        row
        for row in applications
        if parse_iso_date(row["follow_up_date"]) is not None
        and parse_iso_date(row["follow_up_date"]) <= as_of
        and row["application_status"] not in {"OFFER", "EMPLOYER_REJECTED", "WITHDRAWN"}
    ]
    contact_followups = [
        row
        for row in contacts
        if parse_iso_date(row["follow_up_date"]) is not None
        and parse_iso_date(row["follow_up_date"]) <= as_of
    ]

    return {
        "schema_version": "1.0",
        "as_of": as_of.isoformat(),
        "stale_after_days": stale_days,
        "metrics": metrics,
        "conversion_rates": conversion_rates,
        "dashboard": {
            "top_jobs": [_job_summary(row) for row in eligible_top[:top_n]],
            "applications_awaiting_approval": [_application_summary(row) for row in awaiting],
            "sponsorship_needing_verification": [
                _job_summary(row) for row in sponsorship_unknown[:top_n]
            ],
            "stale_jobs": [_job_summary(row) for row in stale[:top_n]],
            "application_followups_due": [
                _application_summary(row) for row in application_followups
            ],
            "contact_followups_due": [
                {
                    "contact_id": row["contact_id"],
                    "full_name": row["full_name"],
                    "company": row["company"],
                    "title": row["title"],
                    "follow_up_date": row["follow_up_date"],
                }
                for row in contact_followups
            ],
            "target_companies": len(companies),
            "resume_versions": len(versions),
            "interview_preparation_records": len(interview_preparation),
        },
        "current_bottleneck": _identify_bottleneck(metrics),
    }


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}%"
    return str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Job Search Dashboard",
        "",
        f"As of: {report['as_of']}",
        "",
    ]
    titles = {
        "job_funnel": "Job Funnel",
        "networking_funnel": "Networking Funnel",
        "interview_funnel": "Interview Funnel",
    }
    for key, title in titles.items():
        lines.extend((f"## {title}", ""))
        for metric, value in report["metrics"][key].items():
            lines.append(f"- {metric.replace('_', ' ').title()}: {value}")
        lines.append("")
    lines.extend(("## Conversion Rates", ""))
    for metric, value in report["conversion_rates"].items():
        lines.append(f"- {metric.replace('_', ' ').title()}: {_display(value)}")
    lines.extend(("", "## Top Jobs", ""))
    top_jobs = report["dashboard"]["top_jobs"]
    if not top_jobs:
        lines.append("- None currently meet all gates.")
    for job in top_jobs:
        lines.append(
            f"- {job['company']} - {job['role_title']} (match {job['match_score']}, "
            f"priority score {job['priority_score']}, {job['priority'] or 'UNRANKED'}, "
            f"{job['work_model']})"
        )
    lines.extend(("", "## Action Queue", ""))
    dashboard = report["dashboard"]
    lines.extend(
        (
            f"- Applications awaiting approval: {len(dashboard['applications_awaiting_approval'])}",
            f"- Sponsorship items needing verification: {len(dashboard['sponsorship_needing_verification'])}",
            f"- Stale jobs: {len(dashboard['stale_jobs'])}",
            f"- Application follow-ups due: {len(dashboard['application_followups_due'])}",
            f"- Contact follow-ups due: {len(dashboard['contact_followups_due'])}",
        )
    )
    bottleneck = report["current_bottleneck"]
    lines.extend(
        (
            "",
            "## Current Bottleneck",
            "",
            f"{bottleneck['stage']}: {bottleneck['explanation']}",
            "",
        )
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate read-only JSON or Markdown campaign dashboards, funnel metrics, conversion "
            "rates, due follow-ups, stale jobs, and a data-driven bottleneck."
        )
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Write to a new file; existing files are refused")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    parser.add_argument("--stale-days", type=int, default=14)
    parser.add_argument("--top", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        parser.error("--as-of must be YYYY-MM-DD")
    if args.stale_days < 1 or args.top < 1:
        parser.error("--stale-days and --top must be positive")
    try:
        workspace = resolve_workspace(args.workspace)
        report = build_report(
            workspace, as_of=as_of, stale_days=args.stale_days, top_n=args.top
        )
        if args.format == "json":
            rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        else:
            rendered = render_markdown(report)
        if args.output:
            atomic_write_text(args.output.expanduser().resolve(), rendered, overwrite=False)
    except (PipelineError, OSError, UnicodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
