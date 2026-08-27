from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from _common import (  # noqa: E402
    APPLICATIONS_FIELDS,
    COMPANIES_FIELDS,
    CONTACTS_FIELDS,
    CSV_SCHEMAS,
    JOBS_FIELDS,
    PipelineError,
    atomic_write_csv,
    contact_priority_rank,
    contact_priority_tier,
    empty_row,
    read_csv_checked,
)


PYTHON = sys.executable
PDF_DEPS = bool(
    importlib.util.find_spec("reportlab")
    and shutil.which("pdfinfo")
    and shutil.which("pdftotext")
    and shutil.which("pdftoppm")
    and shutil.which("pdffonts")
)


class PipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory(prefix="linkedin-pipeline-test-")
        self.temp = Path(self.temp_context.name)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def run_script(
        self,
        script: str,
        *args: object,
        expected: int = 0,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        if extra_env:
            environment.update(extra_env)
        completed = subprocess.run(
            [PYTHON, str(SCRIPTS / script), *(str(arg) for arg in args)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            env=environment,
        )
        if completed.returncode != expected:
            self.fail(
                f"{script} returned {completed.returncode}, expected {expected}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        return completed

    def init_workspace(self, name: str = "campaign") -> Path:
        workspace = self.temp / name
        self.run_script(
            "workspace_init.py", workspace, "--campaign-name", "Offline Test Campaign"
        )
        return workspace

    def add_job(
        self,
        workspace: Path,
        *,
        job_id: str = "job-101",
        company: str = "Acme Product Labs",
        title: str = "Backend Software Engineer",
        url: str = "https://jobs.example.test/backend/101",
        verified_on: str = "2026-08-22",
        sponsorship: str = "UNKNOWN",
        minimum: str = "4",
        match: str = "72",
        priority_score: str = "84",
        description: str = "Build reliable Python APIs and cloud services for a product team.",
    ) -> dict[str, str]:
        completed = self.run_script(
            "job_tracker.py",
            "add-job",
            "--workspace",
            workspace,
            "--job-id",
            job_id,
            "--company",
            company,
            "--title",
            title,
            "--url",
            url,
            "--source",
            "company-careers",
            "--location",
            "United States",
            "--work-model",
            "REMOTE",
            "--first-seen",
            "2026-08-20",
            "--verified-on",
            verified_on,
            "--description",
            description,
            "--sponsorship-status",
            sponsorship,
            "--experience-min-years",
            minimum,
            "--match-score",
            match,
            "--priority-score",
            priority_score,
            "--scoring-dimensions",
            '{"role_alignment":80,"remote_priority":100,"company_priority":75}',
            "--score-rationale",
            "Strong backend evidence and remote preference; sponsorship remains unknown.",
        )
        return json.loads(completed.stdout)


class HelpAndWorkspaceTests(PipelineTestCase):
    def test_owner_preferences_are_opt_in_and_preserve_search_constraints(self) -> None:
        preferences = (SKILL_ROOT / "references" / "owner-preferences.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("only when the candidate confirms", preferences)
        self.assertIn("H-1B", preferences)
        self.assertIn("Amazon", preferences)
        self.assertIn("more than five years", preferences)
        self.assertIn("recruiters first", preferences)
        self.assertIn("currently works at Oracle", preferences)
        self.assertIn("every first-contact LinkedIn connection note", preferences)
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/owner-preferences.md", skill)
        self.assertIn("currently works at Oracle", skill)

        networking = (SKILL_ROOT / "references" / "networking.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Oracle Credential for the Repository Owner", networking)
        self.assertIn("recipient-specific reason", networking)
        self.assertIn("do not invent or imply an Oracle team", networking)

    def test_every_required_cli_has_help(self) -> None:
        scripts = [
            "setup_skill.py",
            "workspace_init.py",
            "job_tracker.py",
            "deduplicate_jobs.py",
            "resume_generator.py",
            "resume_qa.py",
            "reporting.py",
            "target_campaign.py",
        ]
        if PDF_DEPS:
            scripts.append("reference_resume_renderer.py")
        for script in scripts:
            with self.subTest(script=script):
                completed = self.run_script(script, "--help")
                self.assertIn("usage:", completed.stdout.lower())

    @unittest.skipUnless(PDF_DEPS, "PDF dependencies are unavailable")
    def test_reference_renderer_uses_dated_folder_stable_name_and_two_pages(self) -> None:
        source = json.loads((FIXTURES / "resume_source.json").read_text(encoding="utf-8"))
        source["candidate"]["links"] = {
            "linkedin": "https://www.linkedin.com/in/casey-example/",
            "portfolio": "https://casey.example.test/",
        }
        source["experience"] = [
            {**source["experience"][0], "company": f"Example {index}"}
            for index in range(1, 4)
        ]
        source["page_break_after_experience"] = 2
        source_path = self.temp / "source.json"
        source_path.write_text(json.dumps(source), encoding="utf-8")
        output_root = self.temp / "resumes"
        completed = self.run_script(
            "reference_resume_renderer.py",
            "--source", source_path,
            "--output-root", output_root,
            "--date", "2026-08-25",
            "--company", "Example Corp",
            "--job-id", "REQ-101",
            "--role", "Software Engineer",
        )
        metadata = json.loads(completed.stdout)
        pdf = Path(metadata["pdf"])
        self.assertEqual(pdf.name, "SuryaResume.pdf")
        self.assertIn("2026-08-25/example-corp/req-101-software-engineer", pdf.as_posix())
        self.assertEqual(len(__import__("pypdf").PdfReader(pdf).pages), 2)
        second = self.run_script(
            "reference_resume_renderer.py",
            "--source", source_path,
            "--output-root", output_root,
            "--date", "2026-08-25",
            "--company", "Example Corp",
            "--job-id", "REQ-101",
            "--role", "Software Engineer",
            expected=1,
        )
        self.assertIn("Refusing to overwrite", second.stderr)

    def test_workspace_is_external_sanitized_private_and_no_overwrite(self) -> None:
        template = SKILL_ROOT / "assets" / "workspace-template"
        before = {
            path.relative_to(template): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in template.rglob("*")
            if path.is_file()
        }
        workspace = self.init_workspace()
        self.assertTrue((workspace / ".gitignore").is_file())
        self.assertFalse((workspace / "workspace.gitignore").exists())
        self.assertIn("*", (workspace / ".gitignore").read_text(encoding="utf-8"))
        self.assertTrue((workspace / "data" / "search-strategy.md").is_file())
        self.assertTrue((workspace / "data" / "interview-preparation.csv").is_file())
        for relative, fields in CSV_SCHEMAS.items():
            self.assertEqual(
                read_csv_checked(workspace / "data" / relative, fields), [], relative
            )
        metadata = json.loads((workspace / "campaign.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["campaign_name"], "Offline Test Campaign")
        profile = (workspace / "data" / "candidate-profile.md").read_text(encoding="utf-8")
        self.assertNotIn("@gmail.com", profile)

        second = self.run_script(
            "workspace_init.py",
            workspace,
            "--campaign-name",
            "Must Not Replace",
            expected=2,
        )
        self.assertIn("Refusing to overwrite", second.stderr)
        after = {
            path.relative_to(template): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in template.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after, "initializer mutated the installed template")

    def test_workspace_rejects_destination_inside_skill(self) -> None:
        destination = SKILL_ROOT / "runtime-must-not-exist"
        completed = self.run_script(
            "workspace_init.py",
            destination,
            "--campaign-name",
            "Unsafe",
            expected=2,
        )
        self.assertIn("outside the installed skill", completed.stderr)
        self.assertFalse(destination.exists())

    def test_contact_priority_is_recruiter_then_hiring_manager_then_other(self) -> None:
        contacts = [
            {"relationship_type": "TECHNICAL_LEADER", "title": "Staff Engineer"},
            {"relationship_type": "HIRING_MANAGER", "title": "Engineering Manager"},
            {"relationship_type": "OTHER", "title": "Talent Acquisition Partner"},
            {"relationship_type": "RECRUITER", "title": "Agency Recruiter"},
        ]
        ordered = sorted(contacts, key=contact_priority_rank)
        self.assertEqual(
            [contact_priority_tier(row) for row in ordered],
            ["RECRUITER", "RECRUITER", "HIRING_MANAGER", "OTHER"],
        )

    def test_portable_setup_installs_skill_and_imports_resume(self) -> None:
        codex_home = self.temp / "codex-home"
        workspace = self.temp / "portable-campaign"
        resume = self.temp / "candidate-base.md"
        shutil.copy2(FIXTURES / "base_resume.md", resume)

        result = json.loads(
            self.run_script(
                "setup_skill.py",
                "--codex-home",
                codex_home,
                "--workspace",
                workspace,
                "--campaign-name",
                "Portable Test Campaign",
                "--resume",
                resume,
                "--skip-dependency-check",
            ).stdout
        )

        installed = (codex_home / "skills" / "linkedin-job-search-pipeline").resolve()
        self.assertEqual(Path(result["installed_skill"]).resolve(), installed)
        self.assertEqual(Path(result["workspace"]).resolve(), workspace.resolve())
        self.assertEqual(result["stored_resumes"], [resume.name])
        self.assertTrue((installed / "SKILL.md").is_file())
        self.assertTrue((installed / "agents" / "openai.yaml").is_file())
        self.assertTrue((installed / "scripts" / "setup_skill.py").is_file())
        self.assertTrue((installed / "scripts" / "target_campaign.py").is_file())
        self.assertTrue((installed / ".portable-install.json").is_file())
        self.assertFalse((installed / ".git").exists())
        self.assertFalse((installed / "tests").exists())
        self.assertFalse((installed / "README.md").exists())

        target_skill = (codex_home / "skills" / "target-company-job-campaign").resolve()
        self.assertEqual(
            Path(result["installed_target_company_skill"]).resolve(), target_skill
        )
        self.assertTrue((target_skill / "SKILL.md").is_file())
        self.assertTrue((target_skill / "agents" / "openai.yaml").is_file())
        self.assertTrue((target_skill / "references" / "campaign-workflow.md").is_file())
        target_marker = json.loads(
            (target_skill / ".portable-install.json").read_text(encoding="utf-8")
        )
        self.assertEqual(target_marker["skill_name"], "target-company-job-campaign")
        self.assertEqual(target_marker["companion_skill"], "linkedin-job-search-pipeline")

        stored_resume = workspace / "data" / "resumes" / "base" / resume.name
        self.assertEqual(stored_resume.read_bytes(), resume.read_bytes())
        manifest = json.loads(
            (workspace / "data" / "resumes" / "base" / "source-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["resumes"][0]["stored_filename"], resume.name)
        self.assertEqual(
            manifest["resumes"][0]["sha256"], hashlib.sha256(resume.read_bytes()).hexdigest()
        )
        self.assertNotIn(str(resume.parent), json.dumps(manifest))
        self.assertIn("*", (workspace / ".gitignore").read_text(encoding="utf-8"))

        marker_before = (installed / ".portable-install.json").read_bytes()
        duplicate = self.run_script(
            "setup_skill.py",
            "--codex-home",
            codex_home,
            "--workspace",
            self.temp / "must-not-exist",
            "--campaign-name",
            "Must Not Replace",
            "--resume",
            resume,
            "--skip-dependency-check",
            expected=2,
        )
        self.assertIn("Refusing to overwrite installed skill", duplicate.stderr)
        self.assertEqual(marker_before, (installed / ".portable-install.json").read_bytes())
        self.assertFalse((self.temp / "must-not-exist").exists())

    def test_portable_setup_update_preserves_prior_installation(self) -> None:
        codex_home = self.temp / "codex-home"
        self.run_script(
            "setup_skill.py",
            "--codex-home",
            codex_home,
            "--install-only",
            "--skip-dependency-check",
        )
        result = json.loads(
            self.run_script(
                "setup_skill.py",
                "--codex-home",
                codex_home,
                "--install-only",
                "--update",
                "--skip-dependency-check",
            ).stdout
        )
        installed = (codex_home / "skills" / "linkedin-job-search-pipeline").resolve()
        backup = Path(result["backup"]).resolve()
        target_installed = (codex_home / "skills" / "target-company-job-campaign").resolve()
        target_backup = Path(result["target_company_backup"]).resolve()
        self.assertTrue(installed.is_dir())
        self.assertTrue(backup.is_dir())
        self.assertTrue(target_installed.is_dir())
        self.assertTrue(target_backup.is_dir())
        self.assertTrue((backup / ".portable-install.json").is_file())
        self.assertNotEqual(installed, backup)

    def test_target_campaign_requires_two_or_three_unique_companies(self) -> None:
        workspace = self.init_workspace()
        one = self.run_script(
            "target_campaign.py",
            "create",
            "--workspace",
            workspace,
            "--company",
            "Waymo",
            expected=2,
        )
        self.assertIn("exactly 2 or 3", one.stderr)

        four = self.run_script(
            "target_campaign.py",
            "create",
            "--workspace",
            workspace,
            "--company",
            "Waymo",
            "--company",
            "Apple",
            "--company",
            "Google",
            "--company",
            "Microsoft",
            expected=2,
        )
        self.assertIn("exactly 2 or 3", four.stderr)

    def test_target_campaign_creates_private_batch_and_preserves_approval_scope(self) -> None:
        workspace = self.init_workspace()
        created = json.loads(
            self.run_script(
                "target_campaign.py",
                "create",
                "--workspace",
                workspace,
                "--batch-id",
                "ai-platform-batch",
                "--company",
                "Waymo",
                "--company",
                "Apple",
            ).stdout
        )
        self.assertEqual(created["companies"], ["Waymo", "Apple"])
        self.assertEqual(created["phase"], "RESEARCH")
        batch = workspace / "data" / "target-campaigns" / "ai-platform-batch"
        for child in ("research", "decisions", "resumes", "applications", "outreach", "reports"):
            self.assertTrue((batch / child).is_dir())

        self.run_script(
            "target_campaign.py",
            "set-phase",
            "--workspace",
            workspace,
            "--batch-id",
            "ai-platform-batch",
            "--phase",
            "AWAITING_ROLE_APPROVAL",
        )
        approved = json.loads(
            self.run_script(
                "target_campaign.py",
                "approve",
                "--workspace",
                workspace,
                "--batch-id",
                "ai-platform-batch",
                "--checkpoint",
                "ROLES",
                "--scope",
                "Waymo 4702; Apple 200677022",
            ).stdout
        )
        self.assertEqual(approved["approvals"][0]["checkpoint"], "ROLES")
        self.assertEqual(
            approved["approvals"][0]["scope"], "Waymo 4702; Apple 200677022"
        )

        duplicate = self.run_script(
            "target_campaign.py",
            "create",
            "--workspace",
            workspace,
            "--batch-id",
            "ai-platform-batch",
            "--company",
            "Waymo",
            "--company",
            "Apple",
            expected=2,
        )
        self.assertIn("Refusing to overwrite", duplicate.stderr)

    def test_portable_check_reports_missing_poppler_without_writes(self) -> None:
        completed = self.run_script(
            "setup_skill.py",
            "--check-only",
            expected=2,
            extra_env={"PATH": ""},
        )
        self.assertIn("missing Poppler commands", completed.stderr)

    def test_portable_setup_rejects_install_destination_inside_clone(self) -> None:
        unsafe_codex_home = SKILL_ROOT / "must-not-create-codex-home"
        completed = self.run_script(
            "setup_skill.py",
            "--codex-home",
            unsafe_codex_home,
            "--install-only",
            "--skip-dependency-check",
            expected=2,
        )
        self.assertIn("outside this clone", completed.stderr)
        self.assertFalse(unsafe_codex_home.exists())


class TrackerTests(PipelineTestCase):
    def test_score_types_gate_and_application_status_stay_distinct_and_synced(self) -> None:
        workspace = self.init_workspace()
        job = self.add_job(workspace)
        self.assertEqual(job["match_score"], "72")
        self.assertEqual(job["priority_score"], "84")
        self.assertEqual(job["priority"], "HIGH_PRIORITY")
        self.assertEqual(json.loads(job["scoring_dimensions"])["remote_priority"], 100)

        gated = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "NO",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(gated["hard_gate_status"], "PASS")
        self.assertNotIn("sponsorship", json.loads(gated["gate_unknowns"]))
        self.assertEqual(gated["application_status"], "EVALUATED")

        application = json.loads(
            self.run_script(
                "job_tracker.py",
                "add-application",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--resume-version",
                "acme-backend-job-101-v1",
                "--date-prepared",
                "2026-08-22",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(application["application_status"], "READY")
        self.assertEqual(application["priority_score"], "84")
        for status in ("AWAITING_APPROVAL", "APPROVED", "APPLIED"):
            self.run_script(
                "job_tracker.py",
                "set-application-status",
                "--workspace",
                workspace,
                "--application-id",
                application["application_id"],
                "--status",
                status,
            )
        jobs = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)
        applications = read_csv_checked(
            workspace / "data" / "applications.csv", APPLICATIONS_FIELDS
        )
        self.assertEqual(jobs[0]["application_status"], "APPLIED")
        self.assertEqual(applications[0]["application_status"], "APPLIED")
        self.assertTrue(applications[0]["date_approved"])
        self.assertTrue(applications[0]["date_applied"])

        blocked_resume_change = self.run_script(
            "job_tracker.py",
            "set-application-status",
            "--workspace",
            workspace,
            "--application-id",
            application["application_id"],
            "--status",
            "SCREEN",
            "--set",
            "resume_version=corrected-v2",
            expected=2,
        )
        self.assertIn("historical attribution", blocked_resume_change.stderr)
        unchanged = read_csv_checked(
            workspace / "data" / "applications.csv", APPLICATIONS_FIELDS
        )[0]
        self.assertEqual(unchanged["application_status"], "APPLIED")
        self.assertEqual(unchanged["resume_version"], "acme-backend-job-101-v1")

        corrected = json.loads(
            self.run_script(
                "job_tracker.py",
                "set-application-status",
                "--workspace",
                workspace,
                "--application-id",
                application["application_id"],
                "--status",
                "SCREEN",
                "--set",
                "resume_version=corrected-v2",
                "--allow-resume-correction",
                "--correction-note",
                "Corrected a historical tracker transcription error.",
            ).stdout
        )
        self.assertEqual(corrected["resume_version"], "corrected-v2")
        self.assertEqual(corrected["interview_stage"], "SCREEN")
        self.assertIn("RESUME_VERSION_CORRECTION", corrected["notes"])
        job_snapshot = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)[0]
        self.assertEqual(
            job_snapshot["resume_version"],
            "acme-backend-job-101-v1",
            "historical application correction must not replace the job's current resume",
        )

        self.run_script(
            "job_tracker.py",
            "set-application-status",
            "--workspace",
            workspace,
            "--application-id",
            application["application_id"],
            "--status",
            "EMPLOYER_REJECTED",
        )
        self.run_script(
            "job_tracker.py",
            "update-job",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--set",
            "sponsorship_status=NO_SPONSORSHIP",
        )
        re_gated = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "YES",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(re_gated["hard_gate_status"], "REJECT")
        self.assertEqual(re_gated["application_status"], "EMPLOYER_REJECTED")
        preserved = read_csv_checked(
            workspace / "data" / "applications.csv", APPLICATIONS_FIELDS
        )[0]
        self.assertEqual(preserved["application_status"], "EMPLOYER_REJECTED")
        self.assertEqual(preserved["interview_stage"], "SCREEN")

    def test_unknown_sponsorship_continues_scoring_but_blocks_preparation(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace, sponsorship="UNKNOWN")
        gated = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "YES",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(gated["hard_gate_status"], "PASS")
        self.assertIn("sponsorship", json.loads(gated["gate_unknowns"]))
        blocked = self.run_script(
            "job_tracker.py",
            "add-application",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--as-of",
            "2026-08-22",
            expected=2,
        )
        self.assertIn("sponsorship uncertainty", blocked.stderr)

    def test_priority_score_below_fifty_blocks_preparation_independently(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace, match="80", priority_score="45", sponsorship="COMPATIBLE")
        self.run_script(
            "job_tracker.py",
            "evaluate-gate",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--candidate-requires-sponsorship",
            "NO",
            "--as-of",
            "2026-08-22",
        )
        blocked = self.run_script(
            "job_tracker.py",
            "add-application",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--as-of",
            "2026-08-22",
            expected=2,
        )
        self.assertIn("priority_score", blocked.stderr)

    def test_screening_and_employer_rejection_are_not_conflated(self) -> None:
        workspace = self.init_workspace()
        self.add_job(
            workspace,
            job_id="job-no-sponsor",
            url="https://jobs.example.test/backend/no-sponsor",
            sponsorship="NO_SPONSORSHIP",
        )
        screened = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-no-sponsor",
                "--candidate-requires-sponsorship",
                "YES",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(screened["hard_gate_status"], "REJECT")
        self.assertEqual(screened["application_status"], "SCREENED_OUT")
        self.assertIn("sponsorship", screened["rejection_reason"])
        self.run_script(
            "job_tracker.py",
            "add-application",
            "--workspace",
            workspace,
            "--job-id",
            "job-no-sponsor",
            expected=2,
        )

    def test_experience_over_five_is_hard_reject(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace, minimum="6")
        result = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "NO",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(result["hard_gate_status"], "REJECT")
        self.assertIn("exceeds 5-year", result["rejection_reason"])

    def test_stale_or_materially_changed_job_requires_review(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace, verified_on="2026-08-01")
        stale = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "NO",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(stale["hard_gate_status"], "REVIEW_REQUIRED")
        self.assertIn("freshness", stale["gate_unknowns"])

        updated = json.loads(
            self.run_script(
                "job_tracker.py",
                "update-job",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--set",
                "last_verified=2026-08-22",
                "--set",
                "job_description=Changed responsibilities require a new evidence comparison.",
            ).stdout
        )
        self.assertEqual(updated["job_status"], "MATERIALLY_CHANGED")
        self.assertEqual(updated["jd_changed"], "TRUE")
        self.assertEqual(updated["hard_gate_status"], "REVIEW_REQUIRED")
        changed = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--candidate-requires-sponsorship",
                "NO",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(changed["hard_gate_status"], "REVIEW_REQUIRED")
        self.assertIn("re-scored", changed["gate_unknowns"])

    def test_duplicate_add_is_refused_without_modifying_tracker(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace)
        before = (workspace / "data" / "jobs.csv").read_bytes()
        self.run_script(
            "job_tracker.py",
            "add-job",
            "--workspace",
            workspace,
            "--job-id",
            "job-copy",
            "--company",
            "Acme Product Labs",
            "--title",
            "Backend Software Engineer",
            "--url",
            "https://jobs.example.test/backend/101?utm_source=linkedin",
            expected=2,
        )
        self.assertEqual(before, (workspace / "data" / "jobs.csv").read_bytes())

    def test_update_job_rejects_derived_application_status_and_strict_dates(self) -> None:
        workspace = self.init_workspace()
        self.add_job(workspace)
        before = (workspace / "data" / "jobs.csv").read_bytes()
        blocked_status = self.run_script(
            "job_tracker.py",
            "update-job",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--set",
            "application_status=OFFER",
            expected=2,
        )
        self.assertIn("Immutable field", blocked_status.stderr)
        self.assertEqual(before, (workspace / "data" / "jobs.csv").read_bytes())
        malformed_date = self.run_script(
            "job_tracker.py",
            "update-job",
            "--workspace",
            workspace,
            "--job-id",
            "job-101",
            "--set",
            "last_verified=2026-08-22garbage",
            expected=2,
        )
        self.assertIn("must be YYYY-MM-DD", malformed_date.stderr)
        self.assertEqual(before, (workspace / "data" / "jobs.csv").read_bytes())


class DeduplicationTests(PipelineTestCase):
    def _seed(self, workspace: Path) -> None:
        description = (
            "Build Python APIs and reliable cloud services. Own tests, deployments, dashboards, "
            "incident follow-up, and product collaboration."
        )
        rows = [
            empty_row(
                JOBS_FIELDS,
                {
                    "job_id": "source-a",
                    "canonical_job_id": "source-a",
                    "company": "Acme Product Labs",
                    "role_title": "Backend Software Engineer",
                    "url": "https://jobs.example.test/roles/445?utm_source=board",
                    "source": "board-a",
                    "location": "Remote - US",
                    "work_model": "REMOTE",
                    "first_seen": "2026-08-18",
                    "job_status": "DISCOVERED",
                    "job_active": "UNKNOWN",
                    "jd_changed": "UNKNOWN",
                    "job_description": description,
                    "sponsorship_status": "UNKNOWN",
                    "match_score": "70",
                    "priority_score": "80",
                    "priority": "HIGH_PRIORITY",
                    "hard_gate_status": "NOT_EVALUATED",
                    "application_status": "DISCOVERED",
                },
            ),
            empty_row(
                JOBS_FIELDS,
                {
                    "job_id": "source-b",
                    "canonical_job_id": "source-b",
                    "company": "Acme Product Labs",
                    "role_title": "Backend Software Engineer",
                    "url": "https://jobs.example.test/roles/445",
                    "source": "company-careers",
                    "location": "Remote - US",
                    "work_model": "REMOTE",
                    "first_seen": "2026-08-19",
                    "last_verified": "2026-08-22",
                    "job_status": "ACTIVE",
                    "job_active": "TRUE",
                    "jd_changed": "FALSE",
                    "job_description": description,
                    "sponsorship_status": "UNKNOWN",
                    "match_score": "70",
                    "priority_score": "80",
                    "priority": "HIGH_PRIORITY",
                    "hard_gate_status": "PASS",
                    "application_status": "EVALUATED",
                },
            ),
            empty_row(
                JOBS_FIELDS,
                {
                    "job_id": "distinct",
                    "canonical_job_id": "distinct",
                    "company": "Example Cloud",
                    "role_title": "Platform Engineer",
                    "url": "https://careers.example.test/platform/991",
                    "source": "company-careers",
                    "location": "Chicago, IL",
                    "work_model": "HYBRID",
                    "first_seen": "2026-08-20",
                    "last_verified": "2026-08-22",
                    "job_status": "ACTIVE",
                    "job_active": "TRUE",
                    "jd_changed": "FALSE",
                    "job_description": "Operate Kubernetes platform services and internal tooling.",
                    "sponsorship_status": "COMPATIBLE",
                    "match_score": "68",
                    "priority_score": "72",
                    "priority": "GOOD",
                    "hard_gate_status": "PASS",
                    "application_status": "EVALUATED",
                },
            ),
        ]
        atomic_write_csv(workspace / "data" / "jobs.csv", JOBS_FIELDS, rows)

    def test_canonical_dedup_is_auditable_idempotent_and_correctable(self) -> None:
        workspace = self.init_workspace()
        self._seed(workspace)
        canonical_output = self.temp / "canonical.csv"
        report_output = self.temp / "duplicates.json"
        report = json.loads(
            self.run_script(
                "deduplicate_jobs.py",
                "--workspace",
                workspace,
                "--apply",
                "--canonical-output",
                canonical_output,
                "--report",
                report_output,
            ).stdout
        )
        self.assertEqual(report["total_records"], 3)
        self.assertEqual(report["unique_jobs"], 2)
        rows = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)
        by_id = {row["job_id"]: row for row in rows}
        self.assertEqual(by_id["source-a"]["duplicate_of"], "source-b")
        self.assertEqual(by_id["source-a"]["application_status"], "DISCOVERED")
        self.assertEqual(by_id["source-b"]["duplicate_of"], "")
        self.assertEqual(len(json.loads(by_id["source-b"]["duplicate_sources"])), 2)
        self.assertEqual(len(read_csv_checked(canonical_output, JOBS_FIELDS)), 2)
        first_apply = (workspace / "data" / "jobs.csv").read_bytes()
        self.run_script("deduplicate_jobs.py", "--workspace", workspace, "--apply")
        self.assertEqual(first_apply, (workspace / "data" / "jobs.csv").read_bytes())

        # Correct the source record so it is no longer a duplicate; stale generated screening
        # annotations from older pipeline versions must be cleared safely.
        rows = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)
        source_a = next(row for row in rows if row["job_id"] == "source-a")
        source_a["url"] = "https://jobs.example.test/roles/777"
        source_a["company"] = "Different Product Co"
        source_a["role_title"] = "API Engineer"
        source_a["location"] = "New York, NY"
        source_a["job_description"] = "Develop customer APIs in Go for a payments product."
        source_a["application_status"] = "SCREENED_OUT"
        source_a["rejection_reason"] = "duplicate of canonical job source-b"
        atomic_write_csv(workspace / "data" / "jobs.csv", JOBS_FIELDS, rows)
        corrected = json.loads(
            self.run_script("deduplicate_jobs.py", "--workspace", workspace, "--apply").stdout
        )
        self.assertEqual(corrected["unique_jobs"], 3)
        fixed = {
            row["job_id"]: row
            for row in read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)
        }["source-a"]
        self.assertEqual(fixed["duplicate_of"], "")
        self.assertEqual(fixed["application_status"], "DISCOVERED")
        self.assertEqual(fixed["rejection_reason"], "")

        before_refused_apply = (workspace / "data" / "jobs.csv").read_bytes()
        refused = self.run_script(
            "deduplicate_jobs.py",
            "--workspace",
            workspace,
            "--apply",
            "--canonical-output",
            canonical_output,
            expected=2,
        )
        self.assertIn("Refusing to overwrite", refused.stderr)
        self.assertEqual(
            before_refused_apply,
            (workspace / "data" / "jobs.csv").read_bytes(),
            "occupied output paths must be detected before --apply mutates jobs.csv",
        )

    def test_conflicting_explicit_requisitions_are_never_merged(self) -> None:
        workspace = self.init_workspace()
        common = {
            "company": "Acme Product Labs",
            "role_title": "Backend Software Engineer",
            "url": "https://jobs.example.test/shared-posting",
            "location": "Remote - US",
            "work_model": "REMOTE",
            "first_seen": "2026-08-20",
            "last_verified": "2026-08-22",
            "job_status": "ACTIVE",
            "job_active": "TRUE",
            "jd_changed": "FALSE",
            "job_description": "Build the same family of backend services from a shared template.",
            "sponsorship_status": "COMPATIBLE",
            "match_score": "70",
            "priority_score": "80",
            "priority": "HIGH_PRIORITY",
            "hard_gate_status": "PASS",
            "application_status": "EVALUATED",
        }
        rows = [
            empty_row(
                JOBS_FIELDS,
                {**common, "job_id": "req-a", "canonical_job_id": "req-a", "requisition_id": "A-100"},
            ),
            empty_row(
                JOBS_FIELDS,
                {**common, "job_id": "req-b", "canonical_job_id": "req-b", "requisition_id": "B-200"},
            ),
        ]
        atomic_write_csv(workspace / "data" / "jobs.csv", JOBS_FIELDS, rows)
        report = json.loads(
            self.run_script(
                "deduplicate_jobs.py", "--workspace", workspace, "--apply"
            ).stdout
        )
        self.assertEqual(report["unique_jobs"], 2)
        result = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)
        self.assertTrue(all(not row["duplicate_of"] for row in result))


@unittest.skipUnless(PDF_DEPS, "ReportLab and Poppler are required for PDF integration tests")
class ResumeTests(PipelineTestCase):
    def _eligible_workspace(self) -> tuple[Path, str]:
        workspace = self.init_workspace()
        job = self.add_job(workspace)
        gated = json.loads(
            self.run_script(
                "job_tracker.py",
                "evaluate-gate",
                "--workspace",
                workspace,
                "--job-id",
                job["job_id"],
                "--candidate-requires-sponsorship",
                "NO",
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        self.assertEqual(gated["hard_gate_status"], "PASS")
        return workspace, job["jd_hash"]

    def test_versioned_truthful_generation_no_overwrite_and_poppler_qa(self) -> None:
        workspace, jd_hash = self._eligible_workspace()
        source = FIXTURES / "resume_source.json"
        changes = FIXTURES / "resume_changes.json"
        base = json.loads(
            self.run_script(
                "resume_generator.py",
                "--workspace",
                workspace,
                "--source",
                source,
                "--mode",
                "base",
            ).stdout
        )
        self.assertEqual(base["version_id"], "base-resume-v1")
        tailored = json.loads(
            self.run_script(
                "resume_generator.py",
                "--workspace",
                workspace,
                "--source",
                source,
                "--mode",
                "tailored",
                "--job-id",
                "job-101",
                "--company",
                "Acme Product Labs",
                "--role",
                "Backend Software Engineer",
                "--jd-hash",
                jd_hash,
                "--base-resume-version",
                base["version_id"],
                "--changes",
                changes,
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        pdf = Path(tailored["pdf"])
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
        metadata = json.loads(Path(tailored["metadata"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["version_id"], tailored["version_id"])
        self.assertIn("exp.api", json.dumps(metadata["provenance"]))
        self.assertIn("did not synthesize", metadata["truthfulness_note"])

        repeat = self.run_script(
            "resume_generator.py",
            "--workspace",
            workspace,
            "--source",
            source,
            "--mode",
            "tailored",
            "--job-id",
            "job-101",
            "--company",
            "Acme Product Labs",
            "--role",
            "Backend Software Engineer",
            "--jd-hash",
            jd_hash,
            "--base-resume-version",
            base["version_id"],
            "--changes",
            changes,
            "--as-of",
            "2026-08-22",
            expected=2,
        )
        self.assertIn("No meaningful change detected", repeat.stderr)
        self.assertEqual(
            len(list((workspace / "data" / "resumes" / "tailored").glob("*.pdf"))), 1
        )

        render_dir = self.temp / "rendered"
        report_path = self.temp / "qa.json"
        qa = json.loads(
            self.run_script(
                "resume_qa.py",
                "--pdf",
                pdf,
                "--expected-text",
                "Casey Example",
                "--expected-text",
                "casey@example.test",
                "--render-dir",
                render_dir,
                "--report",
                report_path,
            ).stdout
        )
        self.assertEqual(qa["qa_status"], "PASS")
        self.assertTrue(qa["manual_visual_review_required"])
        self.assertEqual(len(list(render_dir.glob("*.png"))), qa["page_count"])
        bad_qa_result = self.run_script(
            "resume_qa.py",
            "--pdf",
            pdf,
            "--expected-text",
            "not-present@example.test",
            expected=1,
        )
        self.assertNotIn("not-present@example.test", bad_qa_result.stdout)
        bad_qa = json.loads(bad_qa_result.stdout)
        self.assertEqual(bad_qa["qa_status"], "FAIL")
        incomplete_qa = json.loads(
            self.run_script(
                "resume_qa.py",
                "--pdf",
                pdf,
                expected=3,
            ).stdout
        )
        self.assertEqual(incomplete_qa["qa_status"], "INCOMPLETE")

        prepared = json.loads(
            self.run_script(
                "job_tracker.py",
                "add-application",
                "--workspace",
                workspace,
                "--job-id",
                "job-101",
                "--resume-version",
                tailored["version_id"],
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        for status in ("AWAITING_APPROVAL", "APPROVED", "APPLIED"):
            self.run_script(
                "job_tracker.py",
                "set-application-status",
                "--workspace",
                workspace,
                "--application-id",
                prepared["application_id"],
                "--status",
                status,
            )
        reordered = json.loads(source.read_text(encoding="utf-8"))
        reordered["experience"][0]["bullets"].reverse()
        reordered_path = self.temp / "resume_source_reordered.json"
        reordered_path.write_text(json.dumps(reordered), encoding="utf-8")
        second_tailored = json.loads(
            self.run_script(
                "resume_generator.py",
                "--workspace",
                workspace,
                "--source",
                reordered_path,
                "--mode",
                "tailored",
                "--job-id",
                "job-101",
                "--company",
                "Acme Product Labs",
                "--role",
                "Backend Software Engineer",
                "--jd-hash",
                jd_hash,
                "--base-resume-version",
                base["version_id"],
                "--changes",
                changes,
                "--as-of",
                "2026-08-22",
            ).stdout
        )
        submitted_application = read_csv_checked(
            workspace / "data" / "applications.csv", APPLICATIONS_FIELDS
        )[0]
        current_job = read_csv_checked(workspace / "data" / "jobs.csv", JOBS_FIELDS)[0]
        self.assertEqual(submitted_application["resume_version"], tailored["version_id"])
        self.assertEqual(current_job["resume_version"], second_tailored["version_id"])
        second_metadata = json.loads(
            Path(second_tailored["metadata"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            second_metadata["base_resume_lineage"]["version_id"], base["version_id"]
        )

    def test_tailored_json_rejects_unproven_claim_and_markdown_is_verbatim_base(self) -> None:
        workspace, jd_hash = self._eligible_workspace()
        base = json.loads(
            self.run_script(
                "resume_generator.py",
                "--workspace",
                workspace,
                "--source",
                FIXTURES / "resume_source.json",
                "--mode",
                "base",
            ).stdout
        )
        missing_lineage = self.run_script(
            "resume_generator.py",
            "--workspace",
            workspace,
            "--source",
            FIXTURES / "resume_source.json",
            "--mode",
            "tailored",
            "--job-id",
            "job-101",
            "--company",
            "Acme Product Labs",
            "--role",
            "Backend Software Engineer",
            "--jd-hash",
            jd_hash,
            "--base-resume-version",
            "missing-base-v99",
            "--changes",
            FIXTURES / "resume_changes.json",
            "--as-of",
            "2026-08-22",
            expected=2,
        )
        self.assertIn("registered base resume", missing_lineage.stderr)
        raw = json.loads((FIXTURES / "resume_source.json").read_text(encoding="utf-8"))
        raw["experience"][0]["bullets"][0] = "Invented unsupported achievement"
        unsupported = self.temp / "unsupported.json"
        unsupported.write_text(json.dumps(raw), encoding="utf-8")
        result = self.run_script(
            "resume_generator.py",
            "--workspace",
            workspace,
            "--source",
            unsupported,
            "--mode",
            "tailored",
            "--job-id",
            "job-101",
            "--company",
            "Acme Product Labs",
            "--role",
            "Backend Software Engineer",
            "--jd-hash",
            jd_hash,
            "--base-resume-version",
            base["version_id"],
            "--changes",
            FIXTURES / "resume_changes.json",
            "--as-of",
            "2026-08-22",
            expected=2,
        )
        self.assertIn("requires source_ids", result.stderr)
        markdown = json.loads(
            self.run_script(
                "resume_generator.py",
                "--workspace",
                workspace,
                "--source",
                FIXTURES / "base_resume.md",
                "--mode",
                "base",
            ).stdout
        )
        self.assertTrue(Path(markdown["pdf"]).is_file())


class ReportingTests(PipelineTestCase):
    def test_reporting_uses_distinct_scores_and_outcomes(self) -> None:
        workspace = self.init_workspace()
        jobs = []
        for index in range(10):
            jobs.append(
                empty_row(
                    JOBS_FIELDS,
                    {
                        "job_id": f"job-{index}",
                        "canonical_job_id": f"job-{index}",
                        "company": f"Product Company {index}",
                        "role_title": "Backend Engineer",
                        "url": f"https://jobs.example.test/{index}",
                        "location": "United States",
                        "work_model": "REMOTE" if index < 8 else "HYBRID",
                        "first_seen": "2026-08-18",
                        "last_verified": "2026-08-22" if index < 9 else "2026-07-01",
                        "job_status": "ACTIVE",
                        "job_active": "TRUE",
                        "jd_changed": "FALSE",
                        "sponsorship_status": "UNKNOWN" if index == 0 else "COMPATIBLE",
                        "match_score": str(55 + index),
                        "priority_score": str(95 - index),
                        "scoring_dimensions": '{"role_alignment":80,"remote_priority":100}',
                        "score_rationale": "Fixture rationale",
                        "priority": "TOP_PRIORITY" if index < 6 else "HIGH_PRIORITY",
                        "hard_gate_status": "PASS",
                        "application_status": "EVALUATED",
                    },
                )
            )
        duplicate = dict(jobs[0])
        duplicate["job_id"] = "job-0-copy"
        duplicate["canonical_job_id"] = "job-0"
        duplicate["duplicate_of"] = "job-0"
        jobs.append(duplicate)
        atomic_write_csv(workspace / "data" / "jobs.csv", JOBS_FIELDS, jobs)

        statuses = [
            "RECRUITER_CONTACTED",
            "EMPLOYER_REJECTED",
            "SCREEN",
            "FINAL",
            "OFFER",
            "WITHDRAWN",
        ]
        applications = []
        for index, status in enumerate(statuses):
            applications.append(
                empty_row(
                    APPLICATIONS_FIELDS,
                    {
                        "application_id": f"app-{index}",
                        "job_id": f"job-{index}",
                        "company": f"Product Company {index}",
                        "role_title": "Backend Engineer",
                        "match_score": str(55 + index),
                        "priority_score": str(95 - index),
                        "priority": "TOP_PRIORITY",
                        "application_status": status,
                        "interview_stage": (
                            "TECHNICAL"
                            if status == "EMPLOYER_REJECTED"
                            else "SCREEN" if status == "WITHDRAWN" else ""
                        ),
                        "date_prepared": "2026-08-19",
                        "date_approved": "2026-08-20",
                        "date_applied": "2026-08-21",
                    },
                )
            )
        applications.append(
            empty_row(
                APPLICATIONS_FIELDS,
                {
                    "application_id": "app-future",
                    "job_id": "job-6",
                    "company": "Product Company 6",
                    "role_title": "Backend Engineer",
                    "match_score": "61",
                    "priority_score": "89",
                    "priority": "HIGH_PRIORITY",
                    "application_status": "APPLIED",
                    "date_prepared": "2026-08-23",
                    "date_approved": "2026-08-23",
                    "date_applied": "2026-08-23",
                },
            )
        )
        atomic_write_csv(
            workspace / "data" / "applications.csv", APPLICATIONS_FIELDS, applications
        )
        contacts = [
            empty_row(
                CONTACTS_FIELDS,
                {
                    "contact_id": "contact-1",
                    "full_name": "Taylor Recruiter",
                    "company": "Product Company 0",
                    "title": "Technical Recruiter",
                    "relationship_type": "RECRUITER",
                    "message_status": "SENT",
                    "response_status": "RESPONDED",
                    "follow_up_date": "2026-08-22",
                },
            )
        ]
        atomic_write_csv(workspace / "data" / "contacts.csv", CONTACTS_FIELDS, contacts)
        companies = [
            empty_row(
                COMPANIES_FIELDS,
                {"company_id": "company-0", "company": "Product Company 0"},
            )
        ]
        atomic_write_csv(workspace / "data" / "companies.csv", COMPANIES_FIELDS, companies)

        report_path = self.temp / "report.json"
        report = json.loads(
            self.run_script(
                "reporting.py",
                "--workspace",
                workspace,
                "--as-of",
                "2026-08-22",
                "--stale-days",
                "3",
                "--output",
                report_path,
            ).stdout
        )
        job_funnel = report["metrics"]["job_funnel"]
        interview = report["metrics"]["interview_funnel"]
        self.assertEqual(job_funnel["jobs_discovered"], 11)
        self.assertEqual(job_funnel["unique_jobs"], 10)
        self.assertEqual(job_funnel["applications_submitted"], 6)
        self.assertEqual(interview["employer_rejections"], 1)
        self.assertEqual(
            interview["recruiter_responses"],
            5,
            "candidate outbound RECRUITER_CONTACTED must not count as a recruiter response",
        )
        self.assertNotIn("SCREENED_OUT", json.dumps(interview))
        top = report["dashboard"]["top_jobs"][0]
        self.assertEqual(top["priority_score"], 95.0)
        self.assertEqual(top["match_score"], 55.0)
        self.assertEqual(len(report["dashboard"]["stale_jobs"]), 1)
        self.assertNotIn(
            "job-9",
            {job["job_id"] for job in report["dashboard"]["top_jobs"]},
            "stale jobs must not appear in the ranked top queue",
        )
        self.assertEqual(
            report["metrics"]["interview_funnel"]["technical_interviews"],
            3,
            "terminal employer rejection must retain the recorded highest interview stage",
        )
        self.assertIsNotNone(report["conversion_rates"]["recruiter_response_per_submitted_pct"])
        refused = self.run_script(
            "reporting.py",
            "--workspace",
            workspace,
            "--as-of",
            "2026-08-22",
            "--output",
            report_path,
            expected=2,
        )
        self.assertIn("Refusing to overwrite", refused.stderr)


if __name__ == "__main__":
    unittest.main()
