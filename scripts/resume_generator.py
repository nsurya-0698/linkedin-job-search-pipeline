#!/usr/bin/env python3
"""Render evidence-backed JSON or verbatim Markdown into an ATS-friendly PDF."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from _common import (
    APPLICATIONS_FIELDS,
    JOBS_FIELDS,
    RESUME_VERSIONS_FIELDS,
    PipelineError,
    atomic_write_bytes,
    atomic_write_csv,
    atomic_write_json,
    boolish,
    csv_path,
    file_lock,
    number,
    parse_iso_date,
    read_csv_checked,
    resolve_workspace,
    sha256_file,
    slugify,
    utc_now,
)


TEXT_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u00a0": " ",
    }
)
PRE_SUBMISSION_APPLICATION_STATUSES = {
    "DISCOVERED",
    "EVALUATED",
    "READY",
    "AWAITING_APPROVAL",
    "APPROVED",
}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").translate(TEXT_TRANSLATION).split())


def _claim_text(
    value: Any,
    *,
    label: str,
    evidence: Mapping[str, Any],
    require_provenance: bool,
) -> tuple[str, list[str]]:
    if isinstance(value, str):
        text = clean_text(value)
        source_ids: list[str] = []
    elif isinstance(value, Mapping):
        text = clean_text(value.get("text", ""))
        raw_sources = value.get("source_ids", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        if not isinstance(raw_sources, list):
            raise PipelineError(f"{label}.source_ids must be a list")
        source_ids = [clean_text(item) for item in raw_sources if clean_text(item)]
    else:
        raise PipelineError(f"{label} must be text or an object containing text/source_ids")
    if not text:
        raise PipelineError(f"{label} text cannot be empty")
    if require_provenance and not source_ids:
        raise PipelineError(
            f"{label} requires source_ids in tailored mode; unsupported claims are not rendered"
        )
    missing = [source_id for source_id in source_ids if source_id not in evidence]
    if missing:
        raise PipelineError(f"{label} references unknown evidence IDs: {', '.join(missing)}")
    return text, source_ids


def _as_list(value: Any, label: str) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    raise PipelineError(f"{label} must be a list")


def validate_json_source(data: Any, *, require_provenance: bool) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PipelineError("Resume JSON must contain an object")
    candidate = data.get("candidate")
    if not isinstance(candidate, dict) or not clean_text(candidate.get("name")):
        raise PipelineError("Resume JSON requires candidate.name")
    evidence = data.get("evidence", {})
    if not isinstance(evidence, dict):
        raise PipelineError("evidence must be an object mapping stable IDs to source facts")
    evidence = {clean_text(key): clean_text(value) for key, value in evidence.items()}
    if any(not key or not value for key, value in evidence.items()):
        raise PipelineError("Evidence IDs and source facts cannot be empty")

    provenance: dict[str, list[str]] = {}

    summary_items = data.get("summary", [])
    if isinstance(summary_items, (str, dict)):
        summary_items = [summary_items]
    summary = []
    for index, item in enumerate(_as_list(summary_items, "summary")):
        text, sources = _claim_text(
            item,
            label=f"summary[{index}]",
            evidence=evidence,
            require_provenance=require_provenance,
        )
        summary.append(text)
        provenance[f"summary[{index}]"] = sources

    skills_value = data.get("skills", {})
    if not isinstance(skills_value, dict):
        raise PipelineError("skills must be an object mapping category names to item lists")
    skills: dict[str, list[str]] = {}
    for category, items in skills_value.items():
        category_text = clean_text(category)
        if not category_text:
            raise PipelineError("Skill category names cannot be empty")
        rendered_items = []
        for index, item in enumerate(_as_list(items, f"skills.{category_text}")):
            text, sources = _claim_text(
                item,
                label=f"skills.{category_text}[{index}]",
                evidence=evidence,
                require_provenance=require_provenance,
            )
            rendered_items.append(text)
            provenance[f"skills.{category_text}[{index}]"] = sources
        if rendered_items:
            skills[category_text] = rendered_items

    def validate_entries(section: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index, raw in enumerate(_as_list(data.get(section, []), section)):
            if not isinstance(raw, dict):
                raise PipelineError(f"{section}[{index}] must be an object")
            entry = {
                key: clean_text(raw.get(key, ""))
                for key in (
                    "organization",
                    "company",
                    "institution",
                    "role",
                    "degree",
                    "name",
                    "location",
                    "start",
                    "end",
                    "url",
                )
            }
            entry_sources = raw.get("source_ids", [])
            if isinstance(entry_sources, str):
                entry_sources = [entry_sources]
            if not isinstance(entry_sources, list):
                raise PipelineError(f"{section}[{index}].source_ids must be a list")
            entry_sources = [clean_text(item) for item in entry_sources if clean_text(item)]
            missing = [item for item in entry_sources if item not in evidence]
            if missing:
                raise PipelineError(
                    f"{section}[{index}] references unknown evidence IDs: {', '.join(missing)}"
                )
            if require_provenance and not entry_sources:
                raise PipelineError(f"{section}[{index}] requires source_ids in tailored mode")
            provenance[f"{section}[{index}]"] = entry_sources
            bullets = []
            for bullet_index, bullet in enumerate(_as_list(raw.get("bullets", []), "bullets")):
                text, sources = _claim_text(
                    bullet,
                    label=f"{section}[{index}].bullets[{bullet_index}]",
                    evidence=evidence,
                    require_provenance=require_provenance,
                )
                bullets.append(text)
                provenance[f"{section}[{index}].bullets[{bullet_index}]"] = sources
            entry["bullets"] = bullets
            if section == "experience" and not (entry["company"] or entry["organization"]):
                raise PipelineError(f"experience[{index}] requires company or organization")
            if section == "education" and not (entry["institution"] or entry["organization"]):
                raise PipelineError(f"education[{index}] requires institution or organization")
            result.append(entry)
        return result

    normalized = {
        "candidate": {key: clean_text(value) for key, value in candidate.items()},
        "summary": summary,
        "skills": skills,
        "experience": validate_entries("experience"),
        "projects": validate_entries("projects"),
        "education": validate_entries("education"),
        "certifications": validate_entries("certifications"),
        "provenance": provenance,
        "evidence": evidence,
    }
    if not any(
        normalized[key]
        for key in ("summary", "skills", "experience", "projects", "education", "certifications")
    ):
        raise PipelineError("Resume source has no renderable content sections")
    return normalized


def parse_markdown_source(text: str) -> list[tuple[str, str]]:
    """Parse a deliberately small ATS-safe Markdown subset without rewriting content."""
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(("paragraph", clean_text(" ".join(paragraph))))
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("# "):
            flush()
            blocks.append(("title", clean_text(line[2:])))
        elif line.startswith("## "):
            flush()
            blocks.append(("section", clean_text(line[3:])))
        elif re.match(r"^[-*]\s+", line):
            flush()
            blocks.append(("bullet", clean_text(re.sub(r"^[-*]\s+", "", line))))
        else:
            paragraph.append(line)
    flush()
    if not blocks or not any(kind == "title" and value for kind, value in blocks):
        raise PipelineError("Markdown source requires a '# Full Name' title")
    if not any(kind in {"section", "bullet", "paragraph"} and value for kind, value in blocks):
        raise PipelineError("Markdown resume contains no body content")
    return blocks


def load_changes(path: Path | None, *, evidence: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid changes JSON: {exc}") from exc
    changes = raw.get("changes") if isinstance(raw, dict) else None
    if not isinstance(changes, list) or not changes:
        raise PipelineError("Changes file must contain a non-empty changes list")
    result = []
    for index, item in enumerate(changes):
        if not isinstance(item, dict):
            raise PipelineError(f"changes[{index}] must be an object")
        normalized = {
            field: clean_text(item.get(field, ""))
            for field in ("change", "reason", "jd_requirement")
        }
        raw_sources = item.get("source_evidence", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        if not isinstance(raw_sources, list):
            raise PipelineError(f"changes[{index}].source_evidence must be a list")
        sources = [clean_text(value) for value in raw_sources if clean_text(value)]
        if any(not normalized[field] for field in normalized) or not sources:
            raise PipelineError(
                f"changes[{index}] requires change, reason, jd_requirement, and source_evidence"
            )
        if evidence is not None:
            missing = [source for source in sources if source not in evidence]
            if missing:
                raise PipelineError(
                    f"changes[{index}] references unknown evidence IDs: {', '.join(missing)}"
                )
        normalized["source_evidence"] = sources
        result.append(normalized)
    return result


def _paragraph(text: str, style: Any, *, bullet: bool = False) -> Any:
    from reportlab.platypus import Paragraph

    escaped = html.escape(clean_text(text))
    if bullet:
        return Paragraph(escaped, style, bulletText="-")
    return Paragraph(escaped, style)


def _styles() -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()["Normal"]
    return {
        "name": ParagraphStyle(
            "ResumeName",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=21,
            alignment=TA_CENTER,
            spaceAfter=2,
            textColor=colors.HexColor("#111111"),
        ),
        "contact": ParagraphStyle(
            "Contact",
            parent=base,
            fontName="Helvetica",
            fontSize=8.7,
            leading=11,
            alignment=TA_CENTER,
            spaceAfter=5,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11.2,
            leading=13,
            spaceBefore=6,
            spaceAfter=2,
            textColor=colors.HexColor("#16263D"),
            borderWidth=0,
            borderPadding=0,
        ),
        "normal": ParagraphStyle(
            "Body",
            parent=base,
            fontName="Helvetica",
            fontSize=9.2,
            leading=11.7,
            spaceAfter=2,
        ),
        "entry": ParagraphStyle(
            "Entry",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=9.6,
            leading=11.7,
            spaceBefore=2,
            spaceAfter=1,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base,
            fontName="Helvetica",
            fontSize=9.2,
            leading=11.5,
            leftIndent=12,
            firstLineIndent=-7,
            bulletIndent=3,
            spaceAfter=1.5,
        ),
    }


def _section_heading(title: str, styles: Mapping[str, Any]) -> list[Any]:
    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable

    return [
        _paragraph(title.upper(), styles["section"]),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#56677A"), spaceAfter=2),
    ]


def build_json_story(source: Mapping[str, Any]) -> list[Any]:
    from reportlab.platypus import Spacer

    styles = _styles()
    story: list[Any] = []
    candidate = source["candidate"]
    story.append(_paragraph(candidate["name"], styles["name"]))
    contact_keys = ("location", "email", "phone", "linkedin", "github", "portfolio")
    contact = " | ".join(candidate.get(key, "") for key in contact_keys if candidate.get(key, ""))
    if contact:
        story.append(_paragraph(contact, styles["contact"]))

    if source["summary"]:
        story.extend(_section_heading("Professional Summary", styles))
        for item in source["summary"]:
            story.append(_paragraph(item, styles["normal"]))

    if source["skills"]:
        story.extend(_section_heading("Technical Skills", styles))
        for category, items in source["skills"].items():
            story.append(
                _paragraph(f"{category}: {', '.join(items)}", styles["normal"])
            )

    section_titles = (
        ("experience", "Experience"),
        ("projects", "Projects"),
        ("education", "Education"),
        ("certifications", "Certifications"),
    )
    for section_key, section_title in section_titles:
        entries = source[section_key]
        if not entries:
            continue
        story.extend(_section_heading(section_title, styles))
        for entry in entries:
            primary = entry.get("role") or entry.get("degree") or entry.get("name")
            organization = (
                entry.get("company") or entry.get("institution") or entry.get("organization")
            )
            lead = " - ".join(value for value in (primary, organization) if value)
            dates = " - ".join(value for value in (entry.get("start"), entry.get("end")) if value)
            details = " | ".join(value for value in (entry.get("location"), dates) if value)
            header = " | ".join(value for value in (lead, details) if value)
            if header:
                story.append(_paragraph(header, styles["entry"]))
            if entry.get("url"):
                story.append(_paragraph(entry["url"], styles["normal"]))
            for bullet in entry["bullets"]:
                story.append(_paragraph(bullet, styles["bullet"], bullet=True))
            story.append(Spacer(1, 1.5))
    return story


def build_markdown_story(blocks: Sequence[tuple[str, str]]) -> list[Any]:
    styles = _styles()
    story: list[Any] = []
    first_title = True
    for kind, value in blocks:
        if kind == "title":
            story.append(_paragraph(value, styles["name"] if first_title else styles["entry"]))
            first_title = False
        elif kind == "section":
            story.extend(_section_heading(value, styles))
        elif kind == "bullet":
            story.append(_paragraph(value, styles["bullet"], bullet=True))
        else:
            story.append(_paragraph(value, styles["normal"]))
    return story


def render_pdf(story: Sequence[Any], output: Path) -> None:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate
    except ImportError as exc:
        raise PipelineError(
            "reportlab is required for PDF generation; install it or use the bundled Codex PDF runtime"
        ) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".resume-", suffix=".pdf", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        document = SimpleDocTemplate(
            str(temporary),
            pagesize=LETTER,
            rightMargin=0.58 * inch,
            leftMargin=0.58 * inch,
            topMargin=0.48 * inch,
            bottomMargin=0.48 * inch,
            title="Resume",
            author="Candidate",
            subject="Professional Resume",
        )
        document.build(list(story))
        data = temporary.read_bytes()
        if not data.startswith(b"%PDF-") or len(data) < 1000:
            raise PipelineError("PDF renderer produced an invalid or unexpectedly small file")
        atomic_write_bytes(output, data, overwrite=False)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _next_version(directory: Path, prefix: str) -> tuple[str, Path, Path]:
    pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.pdf$")
    versions = []
    if directory.is_dir():
        for path in directory.iterdir():
            match = pattern.match(path.name)
            if match:
                versions.append(int(match.group(1)))
    number_value = max(versions, default=0) + 1
    version_id = f"{prefix}-v{number_value}"
    return version_id, directory / f"{version_id}.pdf", directory / f"{version_id}.metadata.json"


def _eligible_job(
    workspace: Path, job_id: str, *, as_of: date, freshness_days: int
) -> dict[str, str]:
    jobs = read_csv_checked(csv_path(workspace, "jobs.csv"), JOBS_FIELDS)
    matching = [row for row in jobs if row["job_id"] == job_id]
    if not matching:
        raise PipelineError(f"Tailored resume job_id is not in jobs.csv: {job_id}")
    job = matching[0]
    if job["duplicate_of"]:
        raise PipelineError(f"Job is a duplicate; tailor only canonical job {job['canonical_job_id']}")
    if job["hard_gate_status"] != "PASS":
        raise PipelineError(f"Job hard gate is {job['hard_gate_status']}, not PASS")
    verified = parse_iso_date(job["last_verified"])
    if (
        boolish(job["job_active"]) is not True
        or verified is None
        or verified > as_of
        or verified < as_of - timedelta(days=freshness_days)
        or job["job_status"] != "ACTIVE"
    ):
        raise PipelineError("Job must be freshly verified and active before tailoring")
    score = number(job["match_score"])
    if score is None or score < 50:
        raise PipelineError("Job needs a meaningful match_score of at least 50 before tailoring")
    priority_score = number(job["priority_score"])
    if priority_score is None or priority_score < 50:
        raise PipelineError("Job needs a weighted priority_score of at least 50 before tailoring")
    try:
        gate_unknowns = set(json.loads(job["gate_unknowns"] or "[]"))
    except json.JSONDecodeError as exc:
        raise PipelineError("Tracked job gate_unknowns is invalid JSON") from exc
    if "sponsorship" in gate_unknowns or "candidate sponsorship requirement" in gate_unknowns:
        raise PipelineError("Resolve decision-changing sponsorship uncertainty before tailoring")
    if job["jd_changed"] == "TRUE":
        raise PipelineError("Job description changed; re-evaluate the role before tailoring")
    return job


def _reject_repeat(
    versions: Sequence[Mapping[str, str]],
    *,
    source_hash: str,
    jd_hash: str,
    changes: Sequence[Any],
    mode: str,
    job_id: str,
) -> None:
    change_summary = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    for version in versions:
        if (
            version["source_sha256"] == source_hash
            and version["jd_hash"] == jd_hash
            and version["change_summary"] == change_summary
            and version["mode"] == mode
            and version["job_id"] == job_id
        ):
            raise PipelineError(
                f"No meaningful change detected; identical output inputs already exist as {version['version_id']}"
            )


def generate(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    source_path = args.source.expanduser().resolve()
    if not source_path.is_file():
        raise PipelineError(f"Resume source does not exist: {source_path}")
    suffix = source_path.suffix.lower()
    if suffix not in {".json", ".md", ".markdown"}:
        raise PipelineError("Resume source must be .json, .md, or .markdown")

    job: dict[str, str] | None = None
    if args.mode == "tailored":
        if not all((args.job_id, args.company, args.role, args.jd_hash, args.base_resume_version)):
            raise PipelineError(
                "Tailored mode requires --job-id, --company, --role, --jd-hash, and --base-resume-version"
            )
        try:
            as_of = date.fromisoformat(args.as_of)
        except ValueError as exc:
            raise PipelineError("as_of must be YYYY-MM-DD") from exc
        job = _eligible_job(
            workspace, args.job_id, as_of=as_of, freshness_days=args.freshness_days
        )
        if clean_text(job["company"]).lower() != clean_text(args.company).lower():
            raise PipelineError("--company does not match the tracked job")
        if clean_text(job["role_title"]).lower() != clean_text(args.role).lower():
            raise PipelineError("--role does not match the tracked job")
        if job["jd_hash"] and job["jd_hash"] != args.jd_hash:
            raise PipelineError("--jd-hash does not match the latest tracked job description")

    evidence: Mapping[str, Any] | None = None
    if suffix == ".json":
        try:
            raw_source = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PipelineError(f"Invalid resume JSON: {exc}") from exc
        normalized = validate_json_source(raw_source, require_provenance=args.mode == "tailored")
        evidence = normalized["evidence"]
        story = build_json_story(normalized)
        provenance = normalized["provenance"]
    else:
        blocks = parse_markdown_source(source_path.read_text(encoding="utf-8"))
        story = build_markdown_story(blocks)
        provenance = {
            "mode": "verbatim_markdown",
            "statement": "Renderer preserved source wording and did not create claims.",
        }

    changes = load_changes(args.changes, evidence=evidence)
    if args.mode == "tailored" and not changes:
        raise PipelineError("Tailored mode requires a non-empty --changes evidence log")

    source_hash = sha256_file(source_path)
    versions_path = csv_path(workspace, "resumes/resume_versions.csv")
    versions = read_csv_checked(versions_path, RESUME_VERSIONS_FIELDS)
    base_lineage: dict[str, str] | None = None
    if args.mode == "tailored":
        base_matches = [
            version for version in versions if version["version_id"] == args.base_resume_version
        ]
        if len(base_matches) != 1 or base_matches[0]["mode"] != "base":
            raise PipelineError(
                "--base-resume-version must identify exactly one registered base resume"
            )
        base_record = base_matches[0]
        base_pdf = Path(base_record["pdf_path"]).expanduser()
        if not base_pdf.is_file():
            raise PipelineError(
                f"Registered base resume artifact is missing: {base_record['pdf_path']}"
            )
        base_lineage = {
            "version_id": base_record["version_id"],
            "source_sha256": base_record["source_sha256"],
            "pdf_path": str(base_pdf.resolve()),
        }
    _reject_repeat(
        versions,
        source_hash=source_hash,
        jd_hash=args.jd_hash or "",
        changes=changes,
        mode=args.mode,
        job_id=args.job_id or "",
    )

    if args.mode == "base":
        prefix = "base-resume"
        directory = workspace / "data" / "resumes" / "base"
    else:
        prefix = "-".join(
            (
                slugify(args.company, "company"),
                slugify(args.role, "role"),
                slugify(args.job_id, "job"),
            )
        )
        directory = workspace / "data" / "resumes" / "tailored"
    version_id, pdf_path, metadata_path = _next_version(directory, prefix)

    metadata = {
        "schema_version": "1.0",
        "version_id": version_id,
        "mode": args.mode,
        "job_id": args.job_id or "",
        "company": args.company or "",
        "role_title": args.role or "",
        "base_resume_version": args.base_resume_version or "",
        "base_resume_lineage": base_lineage,
        "generated_at": utc_now(),
        "jd_hash": args.jd_hash or "",
        "source_sha256": source_hash,
        "source_path": str(source_path),
        "changes": changes,
        "provenance": provenance,
        "truthfulness_note": (
            "This deterministic renderer did not synthesize resume facts. Tailored JSON claims "
            "were required to reference evidence IDs; Markdown was rendered verbatim."
        ),
    }

    render_pdf(story, pdf_path)
    registered = False
    try:
        atomic_write_json(metadata_path, metadata, overwrite=False)
        row = {
            "version_id": version_id,
            "mode": args.mode,
            "job_id": args.job_id or "",
            "company": args.company or "",
            "role_title": args.role or "",
            "base_resume_version": args.base_resume_version or "",
            "generated_at": metadata["generated_at"],
            "jd_hash": args.jd_hash or "",
            "source_sha256": source_hash,
            "source_path": str(source_path),
            "pdf_path": str(pdf_path),
            "metadata_path": str(metadata_path),
            "change_summary": json.dumps(changes, sort_keys=True, separators=(",", ":")),
        }
        with file_lock(versions_path):
            current_versions = read_csv_checked(versions_path, RESUME_VERSIONS_FIELDS)
            _reject_repeat(
                current_versions,
                source_hash=source_hash,
                jd_hash=args.jd_hash or "",
                changes=changes,
                mode=args.mode,
                job_id=args.job_id or "",
            )
            current_versions.append(row)
            atomic_write_csv(versions_path, RESUME_VERSIONS_FIELDS, current_versions)
            registered = True
        if job is not None:
            jobs_path = csv_path(workspace, "jobs.csv")
            applications_path = csv_path(workspace, "applications.csv")
            # Match job_tracker's lock order to avoid deadlocks.
            with file_lock(applications_path):
                with file_lock(jobs_path):
                    applications = read_csv_checked(applications_path, APPLICATIONS_FIELDS)
                    original_applications = [dict(item) for item in applications]
                    jobs = read_csv_checked(jobs_path, JOBS_FIELDS)
                    tracked = next((item for item in jobs if item["job_id"] == args.job_id), None)
                    if tracked is None:
                        raise PipelineError("Tracked job disappeared while registering resume")
                    tracked["resume_version"] = version_id
                    for application in applications:
                        if (
                            application["job_id"] == args.job_id
                            and not application["date_applied"]
                            and application["application_status"]
                            in PRE_SUBMISSION_APPLICATION_STATUSES
                        ):
                            application["resume_version"] = version_id
                    atomic_write_csv(applications_path, APPLICATIONS_FIELDS, applications)
                    try:
                        atomic_write_csv(jobs_path, JOBS_FIELDS, jobs)
                    except Exception:
                        atomic_write_csv(
                            applications_path, APPLICATIONS_FIELDS, original_applications
                        )
                        raise
    except Exception:
        if registered:
            with file_lock(versions_path):
                current_versions = read_csv_checked(versions_path, RESUME_VERSIONS_FIELDS)
                remaining = [item for item in current_versions if item["version_id"] != version_id]
                atomic_write_csv(versions_path, RESUME_VERSIONS_FIELDS, remaining)
        # Only remove artifacts this invocation created; existing versions are never touched.
        for created in (metadata_path, pdf_path):
            try:
                created.unlink()
            except FileNotFoundError:
                pass
        raise
    return {
        "version_id": version_id,
        "pdf": str(pdf_path),
        "metadata": str(metadata_path),
        "qa_status": "NOT_RUN",
        "next_step": "Run resume_qa.py before presenting or using this resume.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a versioned, single-column ATS PDF from structured JSON or verbatim "
            "Markdown. The script renders supplied facts; it never invents resume content."
        )
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--mode", choices=("base", "tailored"), default="tailored")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--company", default="")
    parser.add_argument("--role", default="")
    parser.add_argument("--jd-hash", default="")
    parser.add_argument("--base-resume-version", default="")
    parser.add_argument(
        "--as-of", default=date.today().isoformat(), help="Freshness evaluation date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--freshness-days",
        type=int,
        default=3,
        help="Maximum verification age allowed before tailoring (default: 3)",
    )
    parser.add_argument(
        "--changes",
        type=Path,
        help=(
            "JSON evidence log; required in tailored mode. Each change needs change, reason, "
            "jd_requirement, and source_evidence."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.freshness_days < 0:
        parser.error("--freshness-days cannot be negative")
    try:
        result = generate(args)
    except (PipelineError, OSError, UnicodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True) + "\n", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
