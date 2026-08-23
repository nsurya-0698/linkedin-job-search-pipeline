---
name: linkedin-job-search-pipeline
description: "Run a persistent, evidence-based LinkedIn job-search campaign from a base resume: discover and score roles, track jobs and relationships, tailor resumes, prepare applications and interviews, and learn from outcomes. Use for focused LinkedIn Premium campaigns and job-search dashboards; do not use for mass automation, unsupported candidate claims, or unapproved external sends and submissions."
---

# LinkedIn Job Search Pipeline

Turn a time-boxed LinkedIn Premium period into a truthful, interview-focused campaign. Optimize the funnel from qualified application to recruiter response, interview, final round, and offer—not raw application or connection volume.

## Preserve User Control

Operate in one of three modes and state the active mode when it matters:

- **Research:** discover, verify, deduplicate, compare, score, rank, and report. Do not create external side effects.
- **Preparation:** create local trackers, tailored resume versions, outreach drafts, application answers, and interview packets. Do not send or submit.
- **Execution:** send a message, connection request, or application only after the user explicitly approves that exact action. Reconfirm legally significant or missing application answers immediately before submission.

Never bypass authentication, CAPTCHA, anti-bot controls, rate limits, access controls, or platform restrictions. Use only available tools. If execution is unsupported, prepare the exact manual step.

## Establish the Source of Truth

Do not mutate the installed skill package to store campaign state. Initialize or reuse a separate campaign workspace with `scripts/workspace_init.py`.

When a base resume is supplied and the campaign profile is empty:

1. Register each source filename, version, SHA-256 hash, and extraction date.
2. Extract candidate facts into an evidence ledger with stable source IDs. Write only supported facts to `data/candidate-profile.md`; preserve conflicts and `UNKNOWN` values.
3. Identify the strongest repeated technical capabilities, business/product/project evidence, ownership scope, evidence-backed target and adjacent role families, and recurring gaps.
4. Write the candidate-specific role taxonomy, queries, exclusions, company/work-model priorities, and current gaps to runtime `data/search-strategy.md`.
5. Present unresolved chronology, title, immigration, location, compensation, or claim conflicts before a dependent resume or application step.

Before evaluating jobs:

1. Read the complete base resume and candidate profile.
2. Record source evidence for claims that may appear in a resume, application, or outreach message.
3. Surface conflicting dates, titles, metrics, work authorization, sponsorship need, location, or compensation as unresolved. Do not choose between conflicting sources silently.
4. Treat the base resume as immutable. Store new versions separately and never overwrite a prior version.
5. Do not invent candidate facts or present analytical inferences as facts. Label role/skill-gap inferences and cite the resume evidence behind them. Never infer immigration status, work authorization, sponsorship need, compensation, legal answers, relationships, or accomplishments.

The external campaign workspace's `data/candidate-profile.md` is the candidate-specific source of truth created from supplied sources. Its unresolved items remain blockers for dependent actions. Initialize a fresh profile for a different candidate rather than reusing another person's state.

## Run the Campaign

Use this sequence for each discovery batch:

1. **Discover:** search evidence-backed role families, initially favoring remote roles at large or product-focused technology companies.
2. **Capture:** store the full posting, canonical URL, job/requisition ID, first-seen date, last-verified date, location/work model, requirements, sponsorship evidence, and a stable JD hash.
3. **Deduplicate:** consolidate identical requisitions before scoring or generating resumes. Keep alternate URLs on the canonical record.
4. **Verify:** confirm the role is active and the JD has not materially changed before expensive preparation.
5. **Hard gate:** reject inactive roles, explicit sponsorship incompatibility, impossible location, missing core required qualifications, fundamentally unrelated work, or an explicit experience requirement above five years. Missing evidence is `UNKNOWN`, not automatic rejection.
6. **Match and score:** require at least 50% meaningful responsibility/requirement alignment, then calculate a 0-100 priority score. Raw keyword overlap never establishes eligibility.
7. **Rank:** maintain Top 10, Next 20, and Backup 20 queues for the initial approximately 50-role campaign.
8. **Prepare:** only for user-selected eligible roles, create a minimal truthful resume version, application packet, outreach drafts, and interview topics.
9. **Approve and execute:** present exactly what would be transmitted and wait for approval before the external action.
10. **Record and learn:** update company, contact, application, follow-up, stage, and outcome data; identify the current funnel bottleneck.

## Load Only the Relevant Guidance

- For discovery queries, company prioritization, freshness, and campaign adaptation, read [references/search-strategy.md](references/search-strategy.md).
- Before recommending or rejecting a job, read [references/job-scoring.md](references/job-scoring.md) and [references/sponsorship.md](references/sponsorship.md).
- Before changing resume content or generating a PDF, read [references/resume-tailoring.md](references/resume-tailoring.md).
- Before preparing, approving, submitting, or updating an application, read [references/application-workflow.md](references/application-workflow.md).
- Before identifying contacts or drafting outreach, read [references/networking.md](references/networking.md).
- For a high-priority role or active interview stage, read [references/interview-preparation.md](references/interview-preparation.md).
- For dashboards, conversion analysis, end-of-session reports, or strategy changes, read [references/metrics-and-feedback.md](references/metrics-and-feedback.md).

## Use the Local Automation

Run each script with `--help` before using an unfamiliar mode.

- `workspace_init.py`: create a separate campaign workspace and empty state files without overwriting existing data.
- `job_tracker.py`: add or update normalized job records and application states with validation and atomic writes.
- `deduplicate_jobs.py`: identify canonical records and preserve duplicate-source evidence.
- `resume_generator.py`: render an ATS-friendly PDF from structured, source-backed resume data; it does not invent or rewrite claims.
- `resume_qa.py`: inspect PDF metadata, extracted text, and rendered pages; treat a failed check as a blocker.
- `reporting.py`: produce funnel metrics, due-item summaries, ranked queues, and bottleneck signals from campaign state.

Keep external reads separate from external writes. Local tracker updates are preparation work; LinkedIn messages and job applications are execution work.

## Present Decisions Transparently

For each processed job, report:

- decision: `APPLY`, `BORDERLINE`, `DO_NOT_APPLY`, or `NEEDS_INFORMATION`
- hard-gate result and exact evidence
- meaningful relevance percentage
- priority score and category
- matched requirements with resume evidence
- missing or uncertain requirements
- sponsorship/work-authorization status
- freshness and JD-change status
- recommended resume version and next action

Do not generate a resume for a rejected, stale, duplicate, or unapproved role.

## Close Each Major Session

Summarize jobs discovered/unique/active/rejected/recommended, applications prepared/approved/submitted, contacts and outreach drafts, follow-ups, interviews, resume versions, company history, conversion rates, and the current bottleneck.

End a major campaign with proposed skill improvements based on observed evidence. Do not edit the skill automatically; ask for approval before changing its instructions, scripts, schemas, or strategy.

A/B testing is intentionally out of scope for the first version. Preserve version and outcome fields so it can be added later without rewriting history.
