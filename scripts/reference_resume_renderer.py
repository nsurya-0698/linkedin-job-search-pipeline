#!/usr/bin/env python3
"""Render a reference-matched two-page portal resume in a dated job folder."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from pypdf import PdfReader


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\u2013", "-").replace("\u2014", "-").split())


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", clean(value).lower()).strip("-")
    if not result:
        raise ValueError("Folder component cannot be empty")
    return result


def claim(value: object) -> str:
    return clean(value.get("text", "")) if isinstance(value, dict) else clean(value)


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "name": ParagraphStyle("Name", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=18, alignment=TA_CENTER, spaceAfter=2),
        "contact": ParagraphStyle("Contact", parent=base, fontName="Helvetica", fontSize=10.2, leading=12, alignment=TA_CENTER, spaceAfter=6),
        "section": ParagraphStyle("Section", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=13, spaceBefore=6, spaceAfter=1),
        "body": ParagraphStyle("Body", parent=base, fontName="Helvetica", fontSize=10.2, leading=12.25, spaceAfter=2),
        "skill": ParagraphStyle("Skill", parent=base, fontName="Helvetica", fontSize=10.1, leading=12.1, spaceAfter=1),
        "role": ParagraphStyle("Role", parent=base, fontName="Helvetica-Bold", fontSize=10.3, leading=11.5),
        "date": ParagraphStyle("Date", parent=base, fontName="Helvetica-Oblique", fontSize=10.1, leading=11.5, alignment=TA_RIGHT),
        "company": ParagraphStyle("Company", parent=base, fontName="Helvetica-Oblique", fontSize=10.1, leading=11.5),
        "bullet": ParagraphStyle("Bullet", parent=base, fontName="Helvetica", fontSize=10.05, leading=12.0, leftIndent=17, firstLineIndent=-9, bulletIndent=5, spaceAfter=1.2),
    }


def para(value: str, style: ParagraphStyle, *, trusted_markup: bool = False, bullet: bool = False) -> Paragraph:
    rendered = clean(value) if trusted_markup else html.escape(clean(value))
    return Paragraph(rendered, style, bulletText="•" if bullet else None)


def section(title: str, st: dict[str, ParagraphStyle]) -> list[object]:
    return [para(title.upper(), st["section"]), HRFlowable(width="100%", thickness=1.0, color=colors.black, spaceAfter=3)]


def render(source: dict, output: Path) -> None:
    st = styles()
    summary = [claim(item) for item in source.get("summary", []) if claim(item)]
    if not summary:
        raise ValueError("A job-specific professional summary is required")
    experiences = source.get("experience", [])
    if len(experiences) < 3:
        raise ValueError("At least three experience entries are required for the two-page owner format")

    candidate = source["candidate"]
    links = candidate.get("links", {})
    contact_parts = [html.escape(clean(candidate.get("phone"))), html.escape(clean(candidate.get("email")))]
    for label in ("LinkedIn", "Portfolio"):
        url = clean(links.get(label.lower(), ""))
        if url:
            contact_parts.append(f'<link href="{html.escape(url)}"><u>{label}</u></link>')

    story: list[object] = [para(clean(candidate["name"]).upper(), st["name"]), para(" | ".join(contact_parts), st["contact"], trusted_markup=True)]
    story.extend(section("Professional Summary", st))
    for item in summary:
        story.append(para(item, st["body"]))
    story.extend(section("Technical Skills", st))
    for category, items in source.get("skills", {}).items():
        story.append(para(f"<b>{html.escape(clean(category))}:</b> {html.escape(', '.join(claim(item) for item in items))}", st["skill"], trusted_markup=True))
    story.extend(section("Certifications", st))
    for item in source.get("certifications", []):
        name, url = clean(item.get("name")), clean(item.get("url"))
        value = f'<link href="{html.escape(url)}"><u>{html.escape(name)}</u></link>' if url else html.escape(name)
        story.append(para(value, st["bullet"], trusted_markup=True, bullet=True))
    story.extend(section("Professional Experience", st))

    split_after = int(source.get("page_break_after_experience", 2))
    for index, item in enumerate(experiences):
        role_date = Table([[para(clean(item["role"]), st["role"]), para(f"{clean(item['start'])} - {clean(item['end'])}", st["date"])]], colWidths=[5.75 * inch, 1.45 * inch])
        role_date.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        story.append(role_date)
        company_location = Table([[para(clean(item["company"]), st["company"]), para(clean(item.get("location", "")), st["date"])]], colWidths=[5.75 * inch, 1.45 * inch])
        company_location.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story.append(company_location)
        for bullet in item.get("bullets", []):
            story.append(para(claim(bullet), st["bullet"], bullet=True))
        story.append(Spacer(1, 2))
        if index + 1 == split_after:
            story.append(PageBreak())

    story.extend(section("Education", st))
    for item in source.get("education", []):
        degree = clean(item.get("degree"))
        institution = clean(item.get("institution"))
        end = clean(item.get("end"))
        location = clean(item.get("location"))
        row1 = Table([[para(degree, st["role"]), para(end, st["date"])]], colWidths=[5.4 * inch, 1.8 * inch])
        row2 = Table([[para(institution, st["company"]), para(location, st["date"])]], colWidths=[5.4 * inch, 1.8 * inch])
        for table in (row1, row2):
            table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            story.append(table)

    output.parent.mkdir(parents=True, exist_ok=False)
    doc = SimpleDocTemplate(str(output), pagesize=LETTER, rightMargin=0.6 * inch, leftMargin=0.6 * inch, topMargin=0.48 * inch, bottomMargin=0.48 * inch, title="SuryaResume", author=clean(candidate["name"]), subject="Professional Resume")
    doc.build(story)
    reader = PdfReader(output)
    if len(reader.pages) != 2:
        output.unlink(missing_ok=True)
        raise ValueError(f"Expected exactly 2 pages, generated {len(reader.pages)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    date.fromisoformat(args.date)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    folder = args.output_root / args.date / slug(args.company) / f"{slug(args.job_id)}-{slug(args.role)}"
    output = folder / "SuryaResume.pdf"
    if folder.exists():
        raise SystemExit(f"Refusing to overwrite existing application folder: {folder}")
    render(source, output)
    metadata = {"date": args.date, "company": args.company, "job_id": args.job_id, "role": args.role, "source": str(args.source.resolve()), "pdf": str(output.resolve())}
    (folder / "resume.metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
