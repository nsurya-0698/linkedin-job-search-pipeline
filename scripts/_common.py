#!/usr/bin/env python3
"""Shared, dependency-free helpers for the local job-search pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA_VERSION = "1.0"

JOBS_FIELDS = (
    "job_id",
    "canonical_job_id",
    "duplicate_of",
    "duplicate_sources",
    "linkedin_job_id",
    "requisition_id",
    "company",
    "role_title",
    "url",
    "alternate_urls",
    "source",
    "location",
    "work_model",
    "first_seen",
    "last_verified",
    "job_status",
    "job_active",
    "jd_changed",
    "seniority",
    "job_description",
    "required_qualifications",
    "preferred_qualifications",
    "technologies",
    "responsibilities",
    "sponsorship_status",
    "sponsorship_evidence",
    "experience_min_years",
    "experience_max_years",
    "match_score",
    "priority_score",
    "scoring_dimensions",
    "score_rationale",
    "priority",
    "hard_gate_status",
    "gate_evaluated_at",
    "gate_unknowns",
    "rejection_reason",
    "resume_version",
    "application_status",
    "application_deadline",
    "jd_hash",
    "notes",
)

CONTACTS_FIELDS = (
    "contact_id",
    "full_name",
    "company",
    "title",
    "relationship_type",
    "profile_url",
    "relevance_reason",
    "date_discovered",
    "connection_status",
    "message_status",
    "response_status",
    "last_contacted",
    "follow_up_date",
    "referral_status",
    "notes",
)

APPLICATIONS_FIELDS = (
    "application_id",
    "job_id",
    "company",
    "role_title",
    "url",
    "date_discovered",
    "date_verified",
    "sponsorship_status",
    "match_score",
    "priority_score",
    "scoring_dimensions",
    "score_rationale",
    "priority",
    "resume_version",
    "application_status",
    "date_prepared",
    "date_approved",
    "date_applied",
    "recruiter",
    "hiring_manager",
    "outreach_status",
    "follow_up_date",
    "interview_stage",
    "outcome",
    "notes",
)

COMPANIES_FIELDS = (
    "company_id",
    "company",
    "company_type",
    "product_classification",
    "priority",
    "remote_opportunities",
    "relevant_job_families",
    "sponsorship_observations",
    "previous_applications",
    "recruiters",
    "hiring_managers",
    "networking_contacts",
    "outcomes",
    "last_reviewed",
    "notes",
)

RESUME_VERSIONS_FIELDS = (
    "version_id",
    "mode",
    "job_id",
    "company",
    "role_title",
    "base_resume_version",
    "generated_at",
    "jd_hash",
    "source_sha256",
    "source_path",
    "pdf_path",
    "metadata_path",
    "change_summary",
)

INTERVIEW_PREPARATION_FIELDS = (
    "interview_prep_id",
    "job_id",
    "company",
    "role_title",
    "created_at",
    "technical_topics",
    "system_design_topics",
    "ai_genai_topics",
    "backend_cloud_topics",
    "behavioral_themes",
    "leadership_themes",
    "resume_stories",
    "weak_points",
    "notes",
)

CSV_SCHEMAS: Mapping[str, Sequence[str]] = {
    "jobs.csv": JOBS_FIELDS,
    "contacts.csv": CONTACTS_FIELDS,
    "applications.csv": APPLICATIONS_FIELDS,
    "companies.csv": COMPANIES_FIELDS,
    "resumes/resume_versions.csv": RESUME_VERSIONS_FIELDS,
    "interview-preparation.csv": INTERVIEW_PREPARATION_FIELDS,
}

APPLICATION_STATUSES = (
    "DISCOVERED",
    "EVALUATED",
    "SCREENED_OUT",
    "READY",
    "AWAITING_APPROVAL",
    "APPROVED",
    "APPLIED",
    "RECRUITER_CONTACTED",
    "SCREEN",
    "TECHNICAL",
    "ONSITE",
    "FINAL",
    "OFFER",
    "EMPLOYER_REJECTED",
    "WITHDRAWN",
    "CLOSED_OR_EXPIRED",
)

APPLICATION_TRANSITIONS: Mapping[str, set[str]] = {
    "DISCOVERED": {"EVALUATED", "SCREENED_OUT", "CLOSED_OR_EXPIRED", "WITHDRAWN"},
    "EVALUATED": {"READY", "SCREENED_OUT", "CLOSED_OR_EXPIRED", "WITHDRAWN"},
    "SCREENED_OUT": set(),
    "READY": {"AWAITING_APPROVAL", "SCREENED_OUT", "CLOSED_OR_EXPIRED", "WITHDRAWN"},
    "AWAITING_APPROVAL": {"APPROVED", "SCREENED_OUT", "CLOSED_OR_EXPIRED", "WITHDRAWN"},
    "APPROVED": {"APPLIED", "CLOSED_OR_EXPIRED", "WITHDRAWN"},
    "APPLIED": {"RECRUITER_CONTACTED", "SCREEN", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "RECRUITER_CONTACTED": {"SCREEN", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "SCREEN": {"TECHNICAL", "ONSITE", "FINAL", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "TECHNICAL": {"ONSITE", "FINAL", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "ONSITE": {"FINAL", "OFFER", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "FINAL": {"OFFER", "EMPLOYER_REJECTED", "WITHDRAWN"},
    "OFFER": {"WITHDRAWN"},
    "EMPLOYER_REJECTED": set(),
    "WITHDRAWN": set(),
    "CLOSED_OR_EXPIRED": set(),
}

JOB_STATUSES = (
    "DISCOVERED",
    "ACTIVE",
    "STALE",
    "CLOSED",
    "REMOVED",
    "EXPIRED",
    "MATERIALLY_CHANGED",
)

GATE_STATUSES = ("NOT_EVALUATED", "PASS", "REVIEW_REQUIRED", "REJECT")
TRISTATE = ("TRUE", "FALSE", "UNKNOWN")
SPONSORSHIP_STATUSES = (
    "UNKNOWN",
    "COMPATIBLE",
    "INCOMPATIBLE",
    "SPONSORSHIP_AVAILABLE",
    "NO_SPONSORSHIP",
    "REQUIRES_CONFIRMATION",
)
PRIORITIES = ("", "TOP_PRIORITY", "HIGH_PRIORITY", "GOOD", "BORDERLINE", "DO_NOT_APPLY")


class PipelineError(RuntimeError):
    """An expected, user-actionable pipeline failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return date.today().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, fallback: str = "item") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or fallback


def normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def normalize_url(value: str) -> str:
    """Canonicalize a job URL while preserving identifiers and useful query keys."""
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    scheme = parsed.scheme.lower() or "https"
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    ignored = {
        "trk",
        "trackingid",
        "ref",
        "refid",
        "source",
        "src",
        "campaign",
        "campaignid",
    }
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=False):
        lower = key.lower()
        if lower.startswith("utm_") or lower in ignored:
            continue
        query.append((lower, item.strip()))
    query.sort()
    return urlunsplit((scheme, host + port, path, urlencode(query), ""))


def extract_linkedin_job_id(url: str) -> str:
    patterns = (
        r"/jobs/view/(?:[^/?#]*-)?(\d{5,})",
        r"(?:currentJobId|jobId)=(\d{5,})",
    )
    for pattern in patterns:
        match = re.search(pattern, url, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def parse_json_list(value: str) -> list[Any]:
    if not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(";") if part.strip()]
    return parsed if isinstance(parsed, list) else [parsed]


def stable_json(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def empty_row(fields: Sequence[str], values: Mapping[str, Any] | None = None) -> dict[str, str]:
    values = values or {}
    return {field: str(values.get(field, "")) for field in fields}


def read_csv_checked(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise PipelineError(f"Missing tracker: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        actual = tuple(reader.fieldnames or ())
        expected = tuple(fields)
        if actual != expected:
            raise PipelineError(
                f"Schema mismatch in {path}: expected {list(expected)}, found {list(actual)}"
            )
        rows = []
        for row in reader:
            rows.append({field: (row.get(field) or "").strip() for field in expected})
        return rows


def _fsync_parent(path: Path) -> None:
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, data: bytes, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and path.exists():
        raise PipelineError(f"Refusing to overwrite existing file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if not overwrite:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise PipelineError(f"Refusing to overwrite existing file: {path}") from exc
            temporary.unlink()
        else:
            os.replace(temporary, path)
        _fsync_parent(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_text(path: Path, text: str, *, overwrite: bool = True) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), overwrite=overwrite)


def atomic_write_json(path: Path, value: Any, *, overwrite: bool = True) -> None:
    atomic_write_text(path, stable_json(value, pretty=True), overwrite=overwrite)


def atomic_write_csv(
    path: Path,
    fields: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    *,
    overwrite: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and path.exists():
        raise PipelineError(f"Refusing to overwrite existing file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
            stream.flush()
            os.fsync(stream.fileno())
        if not overwrite:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise PipelineError(f"Refusing to overwrite existing file: {path}") from exc
            temporary.unlink()
        else:
            os.replace(temporary, path)
        _fsync_parent(path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def file_lock(target: Path) -> Iterator[None]:
    """Fail fast if another local process is updating the same tracker."""
    lock = target.with_name(f".{target.name}.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PipelineError(f"Tracker is locked by another process: {lock}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def resolve_workspace(path: str | Path) -> Path:
    workspace = Path(path).expanduser().resolve()
    data = workspace / "data"
    if not data.is_dir():
        raise PipelineError(
            f"Not an initialized campaign workspace (missing data/): {workspace}"
        )
    return workspace


def csv_path(workspace: Path, relative: str) -> Path:
    return workspace / "data" / relative


def boolish(value: str) -> bool | None:
    value = value.strip().upper()
    if value in {"TRUE", "YES", "1", "Y"}:
        return True
    if value in {"FALSE", "NO", "0", "N"}:
        return False
    return None


def number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_iso_date(value: str) -> date | None:
    normalized = value.strip()
    if not normalized:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def validate_iso_date(value: str, label: str) -> str:
    normalized = value.strip()
    if normalized and parse_iso_date(normalized) is None:
        raise PipelineError(f"{label} must be YYYY-MM-DD; received {value!r}")
    return normalized


def validate_score(value: str) -> str:
    if not value:
        return ""
    parsed = number(value)
    if parsed is None or not 0 <= parsed <= 100:
        raise PipelineError(f"match_score must be between 0 and 100; received {value!r}")
    return f"{parsed:g}"


def validate_scoring_dimensions(value: str) -> str:
    """Validate and canonicalize a dimension-to-score JSON object."""
    if not value.strip():
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"scoring_dimensions must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise PipelineError("scoring_dimensions must be a non-empty JSON object")
    normalized: dict[str, float | int] = {}
    for raw_name, raw_score in parsed.items():
        name = str(raw_name).strip()
        score = number(str(raw_score))
        if not name or score is None or not 0 <= score <= 100:
            raise PipelineError(
                "Each scoring dimension needs a non-empty name and numeric score from 0 to 100"
            )
        normalized[name] = int(score) if score.is_integer() else score
    return stable_json(normalized)


def priority_for_score(score: float | None) -> str:
    if score is None:
        return ""
    if score >= 90:
        return "TOP_PRIORITY"
    if score >= 75:
        return "HIGH_PRIORITY"
    if score >= 60:
        return "GOOD"
    if score >= 50:
        return "BORDERLINE"
    return "DO_NOT_APPLY"


def require_choice(value: str, choices: Sequence[str], label: str) -> str:
    normalized = value.strip().upper()
    mapping = {choice.upper(): choice for choice in choices}
    if normalized not in mapping:
        raise PipelineError(f"{label} must be one of: {', '.join(choices)}")
    return mapping[normalized]


def ensure_unique(rows: Sequence[Mapping[str, str]], field: str, value: str) -> None:
    if any(row.get(field) == value for row in rows):
        raise PipelineError(f"Duplicate {field}: {value}")


def print_json(value: Any) -> None:
    print(stable_json(value, pretty=True), end="")
