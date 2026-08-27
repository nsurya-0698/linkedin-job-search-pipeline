# LinkedIn Job Search Pipeline - Implementation Report

## Outcome

`linkedin-job-search-pipeline` is a reusable Codex/ChatGPT skill for a focused LinkedIn Premium job-search campaign. It keeps candidate claims evidence-backed, separates relevance eligibility from opportunity priority, persists local campaign state, prepares ATS resumes and outreach, and requires user approval before any external message or application submission.

Both installed skills are immutable. Personal profiles, source resumes, job descriptions, contacts, applications, reports, and tailored resumes live in a shared external campaign workspace that is ignored by Git by default.

## Files and Architecture

The package contains:

- `SKILL.md`: invocation contract, modes, initialization, workflow, routing, and authorization boundaries.
- `README.md`: portable clone, prerequisite, setup, upgrade, privacy, and usage guide.
- `agents/openai.yaml`: skill-list metadata and default invocation prompt.
- `references/`: scoring, resume, networking, sponsorship, application, interview, metrics, search methodology, and opt-in repository-owner search preferences.
- `scripts/`: the workflow CLIs, a focused target-campaign lifecycle CLI, a portable dual-skill setup CLI, and a shared schema and atomic-I/O module.
- `skills/target-company-job-campaign/`: a separately selectable orchestrator for focused two-to-three-company campaigns.
- `assets/workspace-template/`: sanitized campaign metadata, candidate/search templates, tracker schemas, resume input example, interview tracker, report folder, and fail-closed runtime `.gitignore`.
- `tests/`: offline fixtures and integration tests covering initialization, tracking, gates, deduplication, reporting, truthful/versioned PDF generation, and QA.
- `requirements.txt`: Python PDF dependencies.

The runtime workspace contains the requested operational `data/` tree without making the installed skill writable. This separation prevents live contact, immigration, salary, application, and resume data from being accidentally packaged or pushed with the skill.

## Workflow

The campaign sequence is:

`Discover -> Capture -> Deduplicate -> Verify freshness -> Hard gate -> Meaningful relevance -> Priority score -> Rank -> Prepare -> Approve -> Execute -> Record outcome`

Key invariants:

- `match_score` is the evidence-based JD relevance percentage and must be at least 50.
- `priority_score` is the separate 0-100 opportunity ranking across role, technical, seniority, domain, work-model, company, sponsorship, and interview dimensions.
- Explicit required experience above five years is a hard rejection for this campaign.
- Missing sponsorship language is `UNKNOWN`; candidate work authorization and sponsorship need are never inferred.
- A materially changed or stale JD invalidates the prior evaluation and blocks preparation until reverified and rescored.
- Base resumes are immutable; tailored files are versioned and never overwritten.
- Submitted resume attribution and the highest interview stage are preserved after later status changes.
- Duplicate source rows remain auditable, while only the canonical job can have an application.
- Networking selection uses a strict hierarchy: eligible recruiters first, hiring managers second, and other relevant professionals only after both higher tiers are insufficient.

## Supported Commands

Each script supports `--help`.

```bash
python3 scripts/setup_skill.py --check-only
python3 scripts/setup_skill.py --workspace /path/to/campaign --campaign-name "My Search" --resume /path/to/resume.pdf
python3 scripts/workspace_init.py /path/to/new-campaign --campaign-name "My Search"
python3 scripts/job_tracker.py --help
python3 scripts/deduplicate_jobs.py --workspace /path/to/new-campaign
python3 scripts/resume_generator.py --help
python3 scripts/resume_qa.py --help
python3 scripts/reporting.py --workspace /path/to/new-campaign --format markdown
```

`setup_skill.py` validates a clone, checks Python and Poppler prerequisites, installs both the primary pipeline and target-company orchestrator under the selected Codex home, initializes a separate fail-closed campaign workspace, imports one or more base resumes with SHA-256 metadata, and refuses to overwrite existing state. Recognized installations can be updated explicitly while preserving timestamped backups.

`target_campaign.py` creates a non-overwriting, dated two-to-three-company batch beneath the private workspace. It records ordered lifecycle changes and exact approval scopes for role selection, resume acceptance, application submission, and outreach without treating the manifest itself as authorization.

`job_tracker.py` supports adding/updating jobs, evaluating hard gates, creating one canonical application, validating application-state transitions, and listing state as JSON. Deduplication is read-only unless `--apply` is given. Generators and report outputs refuse to overwrite existing artifacts.

## Automation Boundaries

Research and local preparation may run without repeated approval. External actions do not:

- no silent LinkedIn connection requests or messages;
- no job application submission without approval for the exact job, resume, and answers;
- no inferred work-authorization, sponsorship, compensation, relocation, clearance, or legal attestations;
- no CAPTCHA, authentication, anti-bot, access-control, rate-limit, or platform bypass;
- no automatic skill modification based on campaign results.

If a live integration is unavailable, the skill prepares the local artifact and identifies the manual step.

## Required Inputs

At minimum:

- one base resume or structured candidate source;
- candidate confirmation for conflicting dates, titles, institutions, metrics, or scope;
- work authorization and sponsorship answers before dependent application steps;
- preferred work model/geographies and any compensation boundary when relevant;
- a current job description and canonical job URL for scoring or tailoring.

The PDF renderer consumes approved JSON with evidence IDs or verbatim ATS-safe Markdown. Tailored JSON requires an existing base version and a change log linking every change to source evidence and a JD requirement.

## Tool and Dependency Assumptions

- Python 3 with `reportlab` for PDF generation.
- `pdfplumber` for a text-bounds fallback.
- Poppler commands (`pdfinfo`, `pdftotext`, `pdftoppm`, and `pdffonts`) for PDF QA.
- Available browser/connectors only for live research or execution; the package does not assume unrestricted LinkedIn automation.

On the tested macOS environment, Poppler's `pdftotext -bbox` crashes on some generated PDFs. `resume_qa.py` fails over to `pdfplumber` for bounds validation while normal Poppler text extraction, page metadata, rendering, and font checks continue.

## Validation

- Skill structure/frontmatter validation: passed.
- Python compilation for all required scripts: passed.
- Bundled-runtime offline integration suite: 20/20 passed.
- Portable clean-install, resume-import, dependency-diagnostic, no-overwrite, and safe-update simulations: passed.
- PDF generation: produced selectable-text, letter-size, single-column ATS output.
- Automated PDF checks: structure, page count/size, expected text, blank pages, text bounds, full-page rendering, and font safety passed.
- Manual rendered-page review: no clipping, overlap, broken glyphs, or unreadable content.
- Public-package privacy scan: no candidate email, phone, source-resume path, internal URL, credential, or private workspace data found.
- Independent instruction review: no remaining findings after remediation.
- Independent script audit: high-priority findings remediated and regression-tested.

## Known Limitations

- The skill provides decision rules but does not ship a platform-specific LinkedIn scraper or auto-apply bot.
- Meaningful relevance and priority dimensions require evidence-aware analysis; they are not raw keyword or embedding scores.
- CSV plus file locks is appropriate for one local campaign, not simultaneous multi-host writers.
- Current trackers preserve durable funnel dates and the highest stage, but do not yet provide a full append-only event ledger for every edit.
- Official sponsorship policy can remain unknown until the posting, company, recruiter, or candidate supplies authoritative evidence.
- Candidate conflicts must be resolved by the candidate; source recency alone does not make a disputed fact true.
- A/B testing is intentionally deferred for version one.

## Recommended Improvements

1. Add an append-only event ledger and cohort-maturity reporting.
2. Add CI that installs Python and Poppler dependencies and requires the PDF integration suite.
3. Add opt-in official job-source connectors with freshness and provenance capture.
4. Add human-reviewed semantic deduplication for ambiguous cross-platform postings.
5. Add configurable resume themes while preserving the single-column ATS contract.
6. Add an approval UI that displays exactly what data will be transmitted before execution.

Do not apply these changes automatically. Propose them against observed campaign evidence and wait for approval.
