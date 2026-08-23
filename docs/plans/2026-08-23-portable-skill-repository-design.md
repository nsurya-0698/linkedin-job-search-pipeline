# Portable LinkedIn Job Search Pipeline Repository Design

**Status:** Approved on 2026-08-23

## Goal

Make `linkedin-job-search-pipeline` portable across laptops: clone the repository, run one setup command, provide a base resume, and invoke the skill in Codex.

## Repository Layout

The repository root is the complete skill source tree. It contains `SKILL.md`, agent metadata, references, scripts, sanitized workspace templates, tests, dependency declarations, the implementation report, and the packaged `skill.zip`. A root README is the primary installation and operating guide.

Candidate resumes, contact details, job records, applications, and generated PDFs never live in the repository. Setup creates a separate private campaign workspace protected by a fail-closed `.gitignore`.

## Portable Setup

Add `scripts/setup_skill.py` as the single entry point for a newly cloned repository. It will:

1. Validate the source skill and required files.
2. Install a clean copy into the chosen Codex skills directory, defaulting to `~/.codex/skills/linkedin-job-search-pipeline`.
3. Initialize a separate campaign workspace through the existing initializer.
4. Optionally import one or more base resumes and record SHA-256 source metadata.
5. Check Python packages and Poppler commands, then report exact missing prerequisites.
6. Refuse to overwrite an installed skill, initialized workspace, or existing resume unless the user explicitly selects a safe update mode.

The installer performs no LinkedIn messages, applications, credential access, or network automation.

## README

The README will document the value proposition, safety boundaries, repository structure, platform prerequisites, clone-and-setup quick start, resume import, skill invocation, campaign workflow, tests, upgrades, privacy, troubleshooting, and uninstall steps.

## Failure Handling

Setup uses preflight validation before writing, copies through a staging directory, and cleans incomplete staging data on failure. Existing destinations fail closed. Dependency checks are diagnostic and do not silently install operating-system packages.

## Verification

Tests will cover clean installation with isolated Codex and campaign directories, resume import and hashing, no-overwrite behavior, missing-prerequisite reporting, and installed-skill validation. The complete existing integration suite, PDF generation/QA tests, archive validation, privacy scan, and a clean-clone smoke test must pass before push.

## Delivery

Commit this design separately, implement the approved repository, commit the implementation to `main`, push to `origin`, and verify the remote branch and files.
