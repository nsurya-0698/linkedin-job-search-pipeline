#!/usr/bin/env python3
"""Install the skill and initialize a private campaign workspace."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _common import PipelineError, utc_now
from workspace_init import initialize_workspace


SKILL_NAME = "linkedin-job-search-pipeline"
SCRIPT_PATH = Path(__file__).resolve()
SOURCE_ROOT = SCRIPT_PATH.parent.parent
INSTALL_MARKER = ".portable-install.json"
SUPPORTED_RESUME_SUFFIXES = {".docx", ".json", ".md", ".pdf", ".txt"}
PYTHON_DEPENDENCIES = ("reportlab", "pdfplumber")
POPPLER_COMMANDS = ("pdfinfo", "pdftotext", "pdftoppm", "pdffonts")
INSTALL_ENTRIES = (
    "SKILL.md",
    "agents",
    "assets",
    "references",
    "requirements.txt",
    "scripts",
)
REQUIRED_SOURCE_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "assets/workspace-template/campaign.json",
    "assets/workspace-template/workspace.gitignore",
    "scripts/_common.py",
    "scripts/deduplicate_jobs.py",
    "scripts/job_tracker.py",
    "scripts/reporting.py",
    "scripts/resume_generator.py",
    "scripts/resume_qa.py",
    "scripts/setup_skill.py",
    "scripts/workspace_init.py",
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_digest(source_root: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for entry_name in INSTALL_ENTRIES:
        entry = source_root / entry_name
        if entry.is_file():
            files.append(entry)
        elif entry.is_dir():
            files.extend(
                path
                for path in entry.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
                and path.name != ".DS_Store"
            )
    for path in sorted(files, key=lambda item: item.relative_to(source_root).as_posix()):
        relative = path.relative_to(source_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_source(source_root: Path) -> None:
    for relative in REQUIRED_SOURCE_PATHS:
        path = source_root / relative
        if not path.is_file():
            raise PipelineError(f"Skill source is incomplete: missing {relative}")
    for entry_name in INSTALL_ENTRIES:
        entry = source_root / entry_name
        if not entry.exists():
            raise PipelineError(f"Skill source is incomplete: missing {entry_name}")
        if entry.is_symlink():
            raise PipelineError(f"Refusing symlinked install entry: {entry}")
        if entry.is_dir():
            linked = next((path for path in entry.rglob("*") if path.is_symlink()), None)
            if linked is not None:
                raise PipelineError(f"Refusing symlinked skill content: {linked}")
    frontmatter = (source_root / "SKILL.md").read_text(encoding="utf-8")
    sections = frontmatter.split("---", 2)
    if len(sections) < 3 or f"name: {SKILL_NAME}" not in sections[1]:
        raise PipelineError(f"SKILL.md does not declare name: {SKILL_NAME}")


def dependency_status() -> dict[str, object]:
    missing_python = [
        package for package in PYTHON_DEPENDENCIES if importlib.util.find_spec(package) is None
    ]
    missing_poppler = [command for command in POPPLER_COMMANDS if shutil.which(command) is None]
    return {
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "python_supported": sys.version_info >= (3, 10),
        "missing_python_packages": missing_python,
        "missing_poppler_commands": missing_poppler,
        "ready": sys.version_info >= (3, 10) and not missing_python and not missing_poppler,
    }


def dependency_error(status: dict[str, object], source_root: Path) -> str:
    problems: list[str] = []
    if not status["python_supported"]:
        problems.append("Python 3.10 or newer is required")
    missing_python = status["missing_python_packages"]
    if missing_python:
        problems.append(
            "missing Python packages "
            + ", ".join(str(item) for item in missing_python)
            + f'; run: {sys.executable} -m pip install -r "{source_root / "requirements.txt"}"'
        )
    missing_poppler = status["missing_poppler_commands"]
    if missing_poppler:
        problems.append(
            "missing Poppler commands "
            + ", ".join(str(item) for item in missing_poppler)
            + "; install poppler (macOS: brew install poppler; "
            "Ubuntu/Debian: sudo apt-get install poppler-utils; "
            "Windows: install Poppler and add its bin directory to PATH)"
        )
    return "; ".join(problems)


def _resume_sources(values: list[Path]) -> list[Path]:
    sources: list[Path] = []
    names: set[str] = set()
    for value in values:
        source = value.expanduser().resolve()
        if not source.is_file():
            raise PipelineError(f"Resume source is not a file: {source}")
        if source.suffix.lower() not in SUPPORTED_RESUME_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_RESUME_SUFFIXES))
            raise PipelineError(f"Unsupported resume format for {source.name}; use {supported}")
        normalized = source.name.casefold()
        if normalized in names:
            raise PipelineError(f"Duplicate resume filename: {source.name}")
        names.add(normalized)
        sources.append(source)
    return sources


def _validate_existing_install(destination: Path) -> None:
    if destination.is_symlink():
        raise PipelineError(f"Refusing to update a symlinked installation: {destination}")
    marker = destination / INSTALL_MARKER
    if not marker.is_file():
        raise PipelineError(
            f"Refusing to update unrecognized directory without {INSTALL_MARKER}: {destination}"
        )
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Installed-skill marker is invalid: {marker}") from exc
    if metadata.get("skill_name") != SKILL_NAME:
        raise PipelineError(f"Installed-skill marker belongs to another skill: {marker}")


def _stage_install(source_root: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{SKILL_NAME}.install-", dir=destination.parent)
    )
    try:
        for entry_name in INSTALL_ENTRIES:
            source = source_root / entry_name
            target = staging / entry_name
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    copy_function=shutil.copy2,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
                )
            else:
                shutil.copy2(source, target)
        marker = {
            "installed_at": utc_now(),
            "installer_schema": 1,
            "skill_name": SKILL_NAME,
            "source_digest": _source_digest(source_root),
        }
        (staging / INSTALL_MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        validate_source(staging)
        return staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _stage_workspace(
    destination: Path,
    campaign_name: str,
    template: Path,
    resumes: list[Path],
) -> tuple[Path, list[dict[str, str]]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.setup-", dir=destination.parent)
    )
    staging.rmdir()
    imported: list[dict[str, str]] = []
    try:
        initialize_workspace(staging, campaign_name, template)
        base_directory = staging / "data" / "resumes" / "base"
        for source in resumes:
            target = base_directory / source.name
            if target.exists():
                raise PipelineError(f"Resume destination already exists: {target}")
            shutil.copy2(source, target)
            try:
                target.chmod(0o600)
            except OSError:
                pass
            imported.append(
                {
                    "imported_at": utc_now(),
                    "original_filename": source.name,
                    "sha256": _sha256(target),
                    "stored_filename": target.name,
                }
            )
        manifest = {
            "resumes": imported,
            "schema_version": 1,
        }
        manifest_path = base_directory / "source-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        try:
            manifest_path.chmod(0o600)
        except OSError:
            pass
        return staging, imported
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _install_staged(staging: Path, destination: Path, update: bool) -> Path | None:
    backup: Path | None = None
    if destination.exists():
        if not update:
            raise PipelineError(f"Refusing to overwrite installed skill: {destination}")
        _validate_existing_install(destination)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = destination.parent / f"{destination.name}.backup-{timestamp}"
        if backup.exists():
            raise PipelineError(f"Update backup destination already exists: {backup}")
        os.rename(destination, backup)
    try:
        os.rename(staging, destination)
    except Exception:
        if backup is not None and not destination.exists():
            os.rename(backup, destination)
        raise
    return backup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install linkedin-job-search-pipeline into Codex and initialize a separate, "
            "private campaign workspace. Existing data is never overwritten."
        )
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
        help="Codex home directory (default: CODEX_HOME or ~/.codex)",
    )
    parser.add_argument("--workspace", type=Path, help="New private campaign workspace")
    parser.add_argument("--campaign-name", help="Human-readable campaign name")
    parser.add_argument(
        "--resume",
        action="append",
        default=[],
        type=Path,
        help="Base resume to import; repeat for multiple source versions",
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="Install or update the skill without creating a campaign workspace",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Replace a recognized prior installation and preserve it as a timestamped backup",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate this clone and report dependencies without writing anything",
    )
    parser.add_argument(
        "--skip-dependency-check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source_root = SOURCE_ROOT.resolve()
        validate_source(source_root)
        status = dependency_status()
        if args.check_only:
            print(json.dumps({"dependencies": status, "source_valid": True}, indent=2))
            if not status["ready"]:
                raise PipelineError(dependency_error(status, source_root))
            return 0
        if not status["ready"] and not args.skip_dependency_check:
            raise PipelineError(dependency_error(status, source_root))

        if args.install_only:
            if args.workspace or args.campaign_name or args.resume:
                raise PipelineError(
                    "--install-only cannot be combined with --workspace, --campaign-name, or --resume"
                )
        else:
            if args.workspace is None or not (args.campaign_name or "").strip():
                raise PipelineError(
                    "--workspace and --campaign-name are required unless --install-only is used"
                )
            if not args.resume:
                raise PipelineError("Provide at least one --resume for a new campaign workspace")

        codex_home = args.codex_home.expanduser().resolve()
        install_destination = codex_home / "skills" / SKILL_NAME
        workspace = args.workspace.expanduser().resolve() if args.workspace else None
        if install_destination == source_root or _is_relative_to(
            install_destination, source_root
        ):
            raise PipelineError("Installed skill destination must be outside this clone")
        if install_destination.exists() and not args.update:
            raise PipelineError(f"Refusing to overwrite installed skill: {install_destination}")
        if args.update and install_destination.exists():
            _validate_existing_install(install_destination)
        if workspace is not None:
            if workspace.exists():
                raise PipelineError(f"Refusing to overwrite existing workspace: {workspace}")
            if _is_relative_to(workspace, source_root) or _is_relative_to(
                workspace, install_destination
            ):
                raise PipelineError("Campaign workspace must be outside the source and installed skill")

        resumes = _resume_sources(args.resume)
        install_staging = _stage_install(source_root, install_destination)
        workspace_staging: Path | None = None
        imported: list[dict[str, str]] = []
        try:
            if workspace is not None:
                workspace_staging, imported = _stage_workspace(
                    workspace,
                    args.campaign_name.strip(),
                    install_staging / "assets" / "workspace-template",
                    resumes,
                )
            backup = _install_staged(install_staging, install_destination, args.update)
            install_staging = None
            if workspace is not None and workspace_staging is not None:
                if workspace.exists():
                    raise PipelineError(f"Workspace destination appeared during setup: {workspace}")
                os.rename(workspace_staging, workspace)
                workspace_staging = None
        finally:
            if install_staging is not None:
                shutil.rmtree(install_staging, ignore_errors=True)
            if workspace_staging is not None:
                shutil.rmtree(workspace_staging, ignore_errors=True)

        result = {
            "backup": str(backup) if backup else None,
            "dependencies": status,
            "installed_skill": str(install_destination),
            "resume_count": len(imported),
            "stored_resumes": [item["stored_filename"] for item in imported],
            "workspace": str(workspace) if workspace else None,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
