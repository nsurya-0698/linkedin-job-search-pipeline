---
name: target-company-job-campaign
description: "Run an end-to-end, focused job campaign for a small batch of 2-3 target companies: find and rank matching roles, prepare approved resumes and applications, and coordinate recruiter-first outreach. Use when the user wants one selectable workflow for company targeting; do not use for mass applications or unapproved external sends."
---

# Target Company Job Campaign

Coordinate a complete two-to-three-company campaign while preserving the candidate's control over role selection, resume acceptance, application submission, and outreach. This skill is an orchestrator for the companion `linkedin-job-search-pipeline`; do not duplicate or weaken its source-of-truth, scoring, sponsorship, resume, application, networking, privacy, or platform-control rules.

## Start the Campaign

1. Locate the external campaign workspace. Never store runtime candidate data in either installed skill or in the GitHub clone.
2. Load the companion `linkedin-job-search-pipeline` skill and its relevant references before performing each stage.
3. Read the shared `data/candidate-profile.md`, `data/search-strategy.md`, base-resume manifest, trackers, and unresolved evidence conflicts.
4. Confirm that the workspace represents the current user before applying owner-specific preferences.
5. If companies are not supplied, recommend two or three based on current role fit, sponsorship evidence, posting freshness, work-model preferences, prior outcomes, and application limits. Do not silently reuse stale company assumptions.
6. Create the batch with the companion script:

```bash
python3 ~/.codex/skills/linkedin-job-search-pipeline/scripts/target_campaign.py create \
  --workspace /path/to/private-workspace \
  --company "Company One" \
  --company "Company Two"
```

Read [references/campaign-workflow.md](references/campaign-workflow.md) for lifecycle, checkpoints, artifacts, and completion criteria.

## Execute End to End

Proceed autonomously through research and local preparation where evidence is sufficient. For each batch:

1. Discover fresh roles at the selected companies from authoritative sources.
2. Capture, deduplicate, verify, hard-gate, meaningfully match, score, and rank them with the companion pipeline.
3. Present the eligible roles with evidence and wait for explicit role selection.
4. Create resumes only for approved roles. Follow the companion resume standard, immutable facts, reference layout, folder naming, two-page requirement, and PDF QA.
5. Present the generated PDFs and QA results and wait for explicit resume acceptance.
6. Prepare applications and reconfirm missing or legally significant answers. Present the exact submission payload and wait for approval immediately before each submission or a clearly scoped batch.
7. Submit only approved applications and record confirmation evidence. Never retry an ambiguous submission automatically.
8. Find eligible recruiters first and hiring managers second. Prepare a position-specific LinkedIn connection note or message that truthfully states the application was submitted only after submission is confirmed. When a professional email address is verified from a reliable public or user-provided source, prepare a concise position-specific email; never guess an address.
9. Present every exact recipient, channel, subject, and message and wait for approval immediately before sending.
10. Send only approved outreach, update trackers, schedule follow-ups, and report the batch outcome and next bottleneck.

## Preserve Checkpoints

Use these mandatory checkpoints:

- **Roles:** approval of exact job IDs selected for preparation.
- **Resumes:** approval of exact PDF versions after QA.
- **Submissions:** approval of exact job/application payloads immediately before external submission.
- **Outreach:** approval of exact recipients and text immediately before LinkedIn or email sends.

Record approvals with `target_campaign.py approve`. Approval is scoped to the recorded items and expires if a job description, resume, answer, recipient, channel, or message changes.

## Boundaries

- Do not fabricate candidate facts, recruiter relationships, sponsorship evidence, email addresses, metrics, or application status.
- Do not claim "I applied" in outreach until the corresponding application has a confirmed submission record.
- Do not bypass authentication, CAPTCHA, anti-bot measures, invitation limits, rate limits, or employer controls.
- Do not use bulk or generic outreach. Relevance and truthful personalization are required even within an approved batch.
- If a required capability is unavailable, prepare the exact manual action and stop at the corresponding checkpoint.

## Finish

A batch is complete only when selected applications and approved outreach are recorded, or each remaining item has an explicit blocked/declined outcome. Report companies researched, jobs discovered and rejected, approved resumes, submissions, recipients contacted, follow-ups due, and unresolved blockers.
