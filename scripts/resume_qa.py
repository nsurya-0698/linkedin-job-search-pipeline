#!/usr/bin/env python3
"""Perform hard PDF, extraction, rendering, clipping, and ATS checks on a resume."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence

from _common import PipelineError, atomic_write_json, sha256_file, utc_now


PASS = "PASS"
FAIL = "FAIL"
INCOMPLETE = "INCOMPLETE"


def _check(name: str, status: str, detail: str, *, data: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if data is not None:
        result["data"] = data
    return result


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )


def _parse_pdfinfo(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise PipelineError(f"Invalid rendered PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _bbox_check(pdf: Path, pdftotext: str) -> dict[str, Any]:
    completed = _run((pdftotext, "-bbox", str(pdf), "-"))
    if completed.returncode != 0:
        return _pdfplumber_bounds(
            pdf, fallback_reason=completed.stderr.strip() or "Poppler bbox extraction failed"
        )
    try:
        root = ET.fromstring(completed.stdout)
    except ET.ParseError as exc:
        return _pdfplumber_bounds(pdf, fallback_reason=f"Could not parse Poppler bbox output: {exc}")
    overflow = []
    word_count = 0
    pages = root.findall(".//{*}page")
    for page_number, page in enumerate(pages, start=1):
        try:
            width = float(page.attrib["width"])
            height = float(page.attrib["height"])
        except (KeyError, ValueError):
            continue
        for word in page.findall(".//{*}word"):
            word_count += 1
            try:
                x_min = float(word.attrib["xMin"])
                y_min = float(word.attrib["yMin"])
                x_max = float(word.attrib["xMax"])
                y_max = float(word.attrib["yMax"])
            except (KeyError, ValueError):
                continue
            if x_min < -0.5 or y_min < -0.5 or x_max > width + 0.5 or y_max > height + 0.5:
                overflow.append(
                    {
                        "page": page_number,
                        "text": (word.text or "")[:60],
                        "bounds": [x_min, y_min, x_max, y_max],
                        "page_size": [width, height],
                    }
                )
    if overflow:
        return _check(
            "text_bounds", FAIL, f"Detected {len(overflow)} words outside page bounds", data=overflow[:20]
        )
    if word_count == 0:
        return _check("text_bounds", FAIL, "No positioned words were extracted")
    return _check("text_bounds", PASS, f"All {word_count} extracted words are inside page bounds")


def _pdfplumber_bounds(pdf: Path, *, fallback_reason: str) -> dict[str, Any]:
    """Use character boxes when a platform-specific Poppler bbox command is unstable."""
    try:
        import pdfplumber
    except ImportError:
        return _check(
            "text_bounds",
            INCOMPLETE,
            f"{fallback_reason}; pdfplumber fallback is unavailable",
        )
    overflow = []
    character_count = 0
    try:
        with pdfplumber.open(pdf) as document:
            for page_number, page in enumerate(document.pages, start=1):
                width = float(page.width)
                height = float(page.height)
                for character in page.chars:
                    character_count += 1
                    x_min = float(character.get("x0", 0))
                    x_max = float(character.get("x1", 0))
                    top = float(character.get("top", 0))
                    bottom = float(character.get("bottom", 0))
                    if x_min < -0.5 or top < -0.5 or x_max > width + 0.5 or bottom > height + 0.5:
                        overflow.append(
                            {
                                "page": page_number,
                                "text": str(character.get("text", ""))[:10],
                                "bounds": [x_min, top, x_max, bottom],
                                "page_size": [width, height],
                            }
                        )
    except Exception as exc:
        return _check(
            "text_bounds",
            INCOMPLETE,
            f"{fallback_reason}; pdfplumber fallback failed: {exc}",
        )
    if overflow:
        return _check(
            "text_bounds",
            FAIL,
            f"Detected {len(overflow)} characters outside page bounds using pdfplumber fallback",
            data=overflow[:20],
        )
    if character_count == 0:
        return _check("text_bounds", FAIL, "No positioned characters were extracted")
    return _check(
        "text_bounds",
        PASS,
        f"All {character_count} extracted characters are inside page bounds "
        f"(pdfplumber fallback; Poppler detail: {fallback_reason})",
    )


def inspect_pdf(
    pdf: Path,
    *,
    expected_text: Sequence[str],
    min_text_chars: int,
    max_pages: int,
    render_directory: Path | None,
) -> dict[str, Any]:
    pdf = pdf.expanduser().resolve()
    if not pdf.is_file():
        raise PipelineError(f"PDF does not exist: {pdf}")
    checks: list[dict[str, Any]] = []
    raw = pdf.read_bytes()
    if raw.startswith(b"%PDF-") and len(raw) >= 1000:
        checks.append(_check("pdf_structure", PASS, f"PDF signature present; {len(raw)} bytes"))
    else:
        checks.append(_check("pdf_structure", FAIL, "Missing PDF signature or file is too small"))

    tools = {name: shutil.which(name) for name in ("pdfinfo", "pdftotext", "pdftoppm", "pdffonts")}
    missing_tools = sorted(name for name, location in tools.items() if not location)
    if missing_tools:
        checks.append(
            _check(
                "poppler_tools",
                INCOMPLETE,
                f"Missing required Poppler tool(s): {', '.join(missing_tools)}",
            )
        )
    else:
        checks.append(_check("poppler_tools", PASS, "All required Poppler tools are available"))

    page_count: int | None = None
    page_size = ""
    if tools["pdfinfo"]:
        info_result = _run((tools["pdfinfo"], str(pdf)))
        if info_result.returncode == 0:
            info = _parse_pdfinfo(info_result.stdout)
            try:
                page_count = int(info.get("Pages", ""))
            except ValueError:
                page_count = None
            page_size = info.get("Page size", "")
            if page_count is None or page_count < 1:
                checks.append(_check("page_count", FAIL, "Could not determine a valid page count"))
            elif page_count > max_pages:
                checks.append(
                    _check("page_count", FAIL, f"Resume has {page_count} pages; maximum is {max_pages}")
                )
            else:
                checks.append(_check("page_count", PASS, f"Resume has {page_count} page(s)"))
            if re.search(r"612\s+x\s+792", page_size) or re.search(r"595(?:\.\d+)?\s+x\s+842", page_size):
                checks.append(_check("page_size", PASS, f"Standard ATS page size: {page_size}"))
            else:
                checks.append(_check("page_size", FAIL, f"Unexpected page size: {page_size or 'unknown'}"))
        else:
            checks.append(_check("page_count", INCOMPLETE, info_result.stderr.strip() or "pdfinfo failed"))
            checks.append(_check("page_size", INCOMPLETE, "Page size could not be checked"))
    else:
        checks.extend(
            (
                _check("page_count", INCOMPLETE, "pdfinfo is unavailable"),
                _check("page_size", INCOMPLETE, "pdfinfo is unavailable"),
            )
        )

    extracted = ""
    if tools["pdftotext"]:
        text_result = _run((tools["pdftotext"], "-layout", str(pdf), "-"))
        if text_result.returncode == 0:
            extracted = text_result.stdout
            normalized = " ".join(extracted.split())
            if len(normalized) < min_text_chars:
                checks.append(
                    _check(
                        "text_extraction",
                        FAIL,
                        f"Only {len(normalized)} normalized characters extracted; minimum is {min_text_chars}",
                    )
                )
            elif "\ufffd" in extracted or "\x00" in extracted:
                checks.append(_check("text_extraction", FAIL, "Extracted text contains invalid glyphs"))
            else:
                checks.append(
                    _check(
                        "text_extraction",
                        PASS,
                        f"Extracted {len(normalized)} normalized characters",
                    )
                )
            lower_text = normalized.casefold()
            missing_indices = [
                index
                for index, value in enumerate(expected_text, start=1)
                if value.casefold() not in lower_text
            ]
            if not expected_text:
                checks.append(
                    _check(
                        "required_text",
                        INCOMPLETE,
                        "No --expected-text values were supplied; name/contact verification was not performed",
                    )
                )
            elif missing_indices:
                checks.append(
                    _check(
                        "required_text",
                        FAIL,
                        f"Missing {len(missing_indices)} of {len(expected_text)} expected text value(s)",
                        data={"missing_expected_text_positions": missing_indices},
                    )
                )
            else:
                checks.append(
                    _check(
                        "required_text",
                        PASS,
                        f"Found all {len(expected_text)} expected text value(s)",
                    )
                )
            if page_count:
                page_texts = extracted.split("\f")[:page_count]
                blank_pages = [index + 1 for index, value in enumerate(page_texts) if len(value.strip()) < 20]
                if blank_pages:
                    checks.append(
                        _check("blank_pages", FAIL, "Detected blank or nearly blank pages", data=blank_pages)
                    )
                else:
                    checks.append(_check("blank_pages", PASS, "No blank pages detected"))
            checks.append(_bbox_check(pdf, tools["pdftotext"]))
        else:
            checks.extend(
                (
                    _check("text_extraction", FAIL, text_result.stderr.strip() or "pdftotext failed"),
                    _check("required_text", INCOMPLETE, "Text extraction failed"),
                    _check("text_bounds", INCOMPLETE, "Text extraction failed"),
                )
            )
    else:
        checks.extend(
            (
                _check("text_extraction", INCOMPLETE, "pdftotext is unavailable"),
                _check("required_text", INCOMPLETE, "pdftotext is unavailable"),
                _check("text_bounds", INCOMPLETE, "pdftotext is unavailable"),
            )
        )

    created_temp = render_directory is None
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    if created_temp:
        temp_context = tempfile.TemporaryDirectory(prefix="resume-qa-")
        render_path = Path(temp_context.name)
    else:
        render_path = render_directory.expanduser().resolve()
        if render_path.exists():
            raise PipelineError(f"Refusing to overwrite render directory: {render_path}")
        render_path.mkdir(parents=True)
    try:
        if tools["pdftoppm"]:
            prefix = render_path / "page"
            render_result = _run((tools["pdftoppm"], "-png", "-r", "144", str(pdf), str(prefix)))
            pngs = sorted(render_path.glob("page-*.png"))
            if render_result.returncode != 0 or not pngs:
                checks.append(
                    _check("visual_render", FAIL, render_result.stderr.strip() or "No PNG pages rendered")
                )
            else:
                dimensions = []
                invalid = []
                for png in pngs:
                    try:
                        width, height = _png_dimensions(png)
                        dimensions.append({"file": png.name, "width": width, "height": height})
                        if width < 800 or height < 1000:
                            invalid.append(png.name)
                    except (OSError, PipelineError) as exc:
                        invalid.append(f"{png.name}: {exc}")
                if page_count is not None and len(pngs) != page_count:
                    invalid.append(f"rendered {len(pngs)} pages; expected {page_count}")
                if invalid:
                    checks.append(
                        _check("visual_render", FAIL, "Rendered page validation failed", data=invalid)
                    )
                else:
                    checks.append(
                        _check(
                            "visual_render",
                            PASS,
                            f"Rendered and opened all {len(pngs)} page image(s)",
                            data=dimensions,
                        )
                    )
        else:
            checks.append(_check("visual_render", INCOMPLETE, "pdftoppm is unavailable"))
    finally:
        if temp_context is not None:
            temp_context.cleanup()

    if tools["pdffonts"]:
        fonts_result = _run((tools["pdffonts"], str(pdf)))
        if fonts_result.returncode != 0:
            checks.append(_check("fonts", INCOMPLETE, fonts_result.stderr.strip() or "pdffonts failed"))
        elif re.search(r"\bType 3\b", fonts_result.stdout):
            checks.append(_check("fonts", FAIL, "Type 3 fonts can harm ATS extraction"))
        else:
            checks.append(_check("fonts", PASS, "No Type 3 fonts detected"))
    else:
        checks.append(_check("fonts", INCOMPLETE, "pdffonts is unavailable"))

    statuses = {item["status"] for item in checks}
    overall = FAIL if FAIL in statuses else INCOMPLETE if INCOMPLETE in statuses else PASS
    return {
        "schema_version": "1.0",
        "qa_status": overall,
        "checked_at": utc_now(),
        "pdf": str(pdf),
        "pdf_sha256": sha256_file(pdf),
        "page_count": page_count,
        "page_size": page_size,
        "render_directory": str(render_path) if render_directory is not None else "temporary",
        "checks": checks,
        "manual_visual_review_required": True,
        "note": (
            "Automated rendering detects structural failures, but a human or vision-capable reviewer "
            "must inspect every rendered page before the resume is used."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run ATS-oriented PDF checks: structure, page count/size, text extraction, required "
            "contact text, word bounds, blank pages, Poppler rendering, and font safety."
        )
    )
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument(
        "--expected-text",
        action="append",
        default=[],
        help=(
            "Text that must extract exactly (repeat for name, email, phone, headings, etc.); "
            "omitting this makes QA incomplete"
        ),
    )
    parser.add_argument("--min-text-chars", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument(
        "--render-dir",
        type=Path,
        help="New directory in which to preserve rendered PNGs; existing paths are refused",
    )
    parser.add_argument(
        "--report", type=Path, help="Write JSON QA report to a new path; existing files are refused"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.min_text_chars < 1 or args.max_pages < 1:
        parser.error("--min-text-chars and --max-pages must be positive")
    try:
        report = inspect_pdf(
            args.pdf,
            expected_text=args.expected_text,
            min_text_chars=args.min_text_chars,
            max_pages=args.max_pages,
            render_directory=args.render_dir,
        )
        if args.report:
            atomic_write_json(args.report.expanduser().resolve(), report, overwrite=False)
    except (PipelineError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True) + "\n", end="")
    return {PASS: 0, FAIL: 1, INCOMPLETE: 3}[report["qa_status"]]


if __name__ == "__main__":
    sys.exit(main())
