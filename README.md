# LinkedIn Job Search Pipeline

A portable Codex skill for running a persistent, evidence-based job search from a verified base resume—without turning LinkedIn into a mass-automation project.

Clone this repository on any laptop, run one setup command, provide the candidate's resume, and invoke `$linkedin-job-search-pipeline` in Codex.

## What It Does

- Builds a candidate source of truth without inventing skills, dates, metrics, or immigration answers.
- Discovers, deduplicates, freshness-checks, gates, scores, and ranks job opportunities.
- Separates meaningful resume relevance from opportunity priority.
- Creates versioned, ATS-friendly tailored resumes with PDF text and render QA.
- Prepares relationship-focused LinkedIn outreach drafts and interview packets.
- Prioritizes relevant recruiters first, hiring managers second, and other professional contacts last in every networking batch.
- Tracks companies, jobs, contacts, applications, follow-ups, stages, and outcomes.
- Requires explicit approval before any LinkedIn message or application submission.
- Includes opt-in repository-owner search preferences without bundling the owner's resume or campaign history.

## Portable Quick Start

### 1. Clone

```bash
git clone https://github.com/nsurya-0698/linkedin-job-search-pipeline.git
cd linkedin-job-search-pipeline
```

### 2. Check prerequisites

```bash
python3 scripts/setup_skill.py --check-only
```

The command reports exactly what is missing. The required baseline is:

- Python 3.10 or newer
- Python packages from `requirements.txt`
- Poppler commands: `pdfinfo`, `pdftotext`, `pdftoppm`, and `pdffonts`

Install the Python packages with:

```bash
python3 -m pip install -r requirements.txt
```

Install Poppler using the package manager for the laptop:

| Platform | Command or action |
|---|---|
| macOS | `brew install poppler` |
| Ubuntu/Debian | `sudo apt-get install poppler-utils` |
| Windows | Install a Poppler distribution and add its `bin` directory to `PATH` |

### 3. Install the skill and create a private campaign

```bash
python3 scripts/setup_skill.py \
  --workspace "$HOME/job-search-campaign" \
  --campaign-name "My Job Search" \
  --resume "/path/to/base-resume.pdf"
```

Repeat `--resume` when the candidate has multiple source versions:

```bash
python3 scripts/setup_skill.py \
  --workspace "$HOME/job-search-campaign" \
  --campaign-name "My Job Search" \
  --resume "/path/to/resume-v1.pdf" \
  --resume "/path/to/resume-v2.pdf"
```

The setup command:

1. Installs a clean skill copy at `~/.codex/skills/linkedin-job-search-pipeline`.
2. Creates the campaign workspace outside the installed skill.
3. Copies base resumes into the private workspace.
4. Records each imported filename and SHA-256 hash.
5. Refuses to overwrite existing installations, workspaces, or resumes.

Set `CODEX_HOME` or pass `--codex-home /custom/path` when Codex uses a non-default home directory.

### 4. Run it in Codex

Start a new Codex task and enter:

```text
Use $linkedin-job-search-pipeline to initialize my candidate profile from the base resumes in my campaign workspace.
```

Then provide the workspace path printed by setup. Resolve any conflicting dates, titles, institutions, scope, or metrics before dependent tailoring or applications.

## Campaign Workflow

```text
Discover
  → Capture
  → Deduplicate
  → Verify freshness
  → Hard gate
  → Meaningful relevance
  → Priority score
  → Rank
  → Prepare
  → Approve
  → Execute
  → Record outcome
```

The skill supports three modes:

- **Research:** read, verify, score, and report without external side effects.
- **Preparation:** create local drafts, trackers, tailored PDFs, and interview materials.
- **Execution:** send or submit only after approval for the exact action.

Networking batches follow a strict contact hierarchy: eligible recruiters first, hiring managers second, and other relevant professionals only when the higher tiers cannot fill the batch. Relevance and truthful personalization remain prerequisites at every tier.

## Privacy Model

The GitHub repository contains only skill code, sanitized templates, tests, documentation, and fixtures. It must not contain real resumes, contact data, immigration answers, salary expectations, job history, applications, or generated tailored resumes.

The repository does contain an explicitly authorized, opt-in owner-preferences reference for Surya's portable search constraints. It is used only after confirming the campaign belongs to Surya and is never inherited by another candidate. The source resume and detailed career record remain private.

Every initialized campaign workspace receives a fail-closed `.gitignore`:

```gitignore
*
!.gitignore
```

This separation keeps the installed skill reusable and candidate data local. Do not weaken the campaign privacy guard or move a populated campaign workspace into this repository.

## Repository Structure

```text
linkedin-job-search-pipeline/
├── SKILL.md
├── README.md
├── IMPLEMENTATION_REPORT.md
├── requirements.txt
├── skill.zip
├── agents/
│   └── openai.yaml
├── assets/
│   └── workspace-template/
├── references/
│   ├── application-workflow.md
│   ├── interview-preparation.md
│   ├── job-scoring.md
│   ├── metrics-and-feedback.md
│   ├── networking.md
│   ├── owner-preferences.md
│   ├── resume-tailoring.md
│   ├── search-strategy.md
│   └── sponsorship.md
├── scripts/
│   ├── setup_skill.py
│   ├── workspace_init.py
│   ├── job_tracker.py
│   ├── deduplicate_jobs.py
│   ├── resume_generator.py
│   ├── resume_qa.py
│   └── reporting.py
├── tests/
└── docs/plans/
```

## Useful Commands

Install the skill without creating another campaign:

```bash
python3 scripts/setup_skill.py --install-only
```

Upgrade a recognized installation while keeping a timestamped backup:

```bash
git pull --ff-only
python3 scripts/setup_skill.py --install-only --update
```

Initialize an additional campaign directly from the installed skill:

```bash
python3 ~/.codex/skills/linkedin-job-search-pipeline/scripts/workspace_init.py \
  "$HOME/another-job-search" \
  --campaign-name "Another Search"
```

View command help before an unfamiliar operation:

```bash
python3 scripts/job_tracker.py --help
python3 scripts/deduplicate_jobs.py --help
python3 scripts/resume_generator.py --help
python3 scripts/resume_qa.py --help
python3 scripts/reporting.py --help
```

## Validation

Run the complete offline suite:

```bash
python3 -m unittest discover -s tests -v
```

The suite covers workspace isolation, hard gates, state transitions, deduplication, relevance and priority separation, reporting, portable installation, resume lineage, PDF generation, and PDF QA. PDF integration tests require the dependencies listed above.

Validate the skill structure with Codex's bundled skill validator when available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Updating and Uninstalling

`--update` only replaces an installation created by this setup script. The previous installation is preserved beside it as a timestamped backup. Campaign workspaces are never modified during an install-only update.

To uninstall, move `~/.codex/skills/linkedin-job-search-pipeline` out of the Codex skills directory. Campaign workspaces remain separate and must be retained or removed deliberately by their owner.

## Safety Boundaries

This repository does not include a LinkedIn scraper or auto-apply bot. The skill never grants itself permission to:

- fabricate candidate facts or relationships;
- infer work authorization, sponsorship need, compensation, or legal answers;
- bypass authentication, CAPTCHA, anti-bot, access, or rate controls;
- send messages or submit applications without exact user approval;
- overwrite base resumes or prior tailored versions;
- automatically rewrite its own instructions based on campaign results.

See [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) for architecture, validation details, and known limitations.
