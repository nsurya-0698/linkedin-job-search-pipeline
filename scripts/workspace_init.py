#!/usr/bin/env python3
"""Create a writable campaign workspace from the skill's sanitized template."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from _common import CSV_SCHEMAS, PipelineError, SCHEMA_VERSION, read_csv_checked, slugify, utc_now


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parent.parent
DEFAULT_TEMPLATE = SKILL_ROOT / "assets" / "workspace-template"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_template(template: Path) -> None:
    if not template.is_dir():
        raise PipelineError(f"Workspace template is missing: {template}")
    candidate_profile = template / "data" / "candidate-profile.md"
    if not candidate_profile.is_file():
        raise PipelineError(f"Template is incomplete: missing {candidate_profile}")
    for relative, fields in CSV_SCHEMAS.items():
        read_csv_checked(template / "data" / relative, fields)


def initialize_workspace(destination: Path, campaign_name: str, template: Path = DEFAULT_TEMPLATE) -> Path:
    destination = destination.expanduser().resolve()
    template = template.expanduser().resolve()
    skill_root = SKILL_ROOT.resolve()

    if destination == skill_root or _is_relative_to(destination, skill_root):
        raise PipelineError(
            "Campaign workspaces must be outside the installed skill directory; "
            f"choose a separate path instead of {destination}"
        )
    if destination.exists():
        raise PipelineError(f"Refusing to overwrite existing destination: {destination}")
    if not campaign_name.strip():
        raise PipelineError("Campaign name cannot be empty")

    _validate_template(template)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.init.lock"
    try:
        lock_descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PipelineError(f"Another initializer is using this destination: {lock}") from exc

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    try:
        os.write(lock_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(lock_descriptor)
        shutil.copytree(template, staging, dirs_exist_ok=True, copy_function=shutil.copy2)

        gitignore_template = staging / "workspace.gitignore"
        if not gitignore_template.is_file():
            raise PipelineError("Template is incomplete: missing workspace.gitignore privacy guard")
        os.replace(gitignore_template, staging / ".gitignore")

        metadata_path = staging / "campaign.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(
            {
                "campaign_id": slugify(campaign_name, "campaign"),
                "campaign_name": campaign_name.strip(),
                "created_at": utc_now(),
                "schema_version": SCHEMA_VERSION,
            }
        )
        # This file exists only in staging, so a normal write cannot mutate the package.
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if destination.exists():
            raise PipelineError(f"Destination appeared during initialization: {destination}")
        os.rename(staging, destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize a separate, writable job-search campaign workspace from "
            "the skill's sanitized template. Existing destinations are never overwritten."
        )
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="New campaign workspace directory (must not already exist or be inside the skill)",
    )
    parser.add_argument(
        "--campaign-name",
        required=True,
        help="Human-readable campaign name stored in campaign.json",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        destination = initialize_workspace(args.destination, args.campaign_name, args.template)
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
