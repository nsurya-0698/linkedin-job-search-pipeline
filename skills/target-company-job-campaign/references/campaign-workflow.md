# Campaign Workflow

## Batch Artifacts

`target_campaign.py create` writes only orchestration state beneath the shared private workspace:

```text
data/target-campaigns/<batch-id>/
├── campaign.json
├── research/
├── decisions/
├── resumes/
├── applications/
├── outreach/
└── reports/
```

The normalized CSV trackers under `data/` remain authoritative. Batch files may contain snapshots, decision reports, approved artifact references, and execution evidence; they must not replace the trackers or base-resume evidence ledger.

## Lifecycle

Advance phases in order with `target_campaign.py set-phase`:

1. `RESEARCH`
2. `AWAITING_ROLE_APPROVAL`
3. `RESUME_PREPARATION`
4. `AWAITING_RESUME_APPROVAL`
5. `APPLICATION_PREPARATION`
6. `AWAITING_SUBMISSION_APPROVAL`
7. `APPLICATION_EXECUTION`
8. `OUTREACH_PREPARATION`
9. `AWAITING_OUTREACH_APPROVAL`
10. `OUTREACH_EXECUTION`
11. `COMPLETE`

Use `BLOCKED` only when required user information, authentication, platform state, or source evidence prevents safe progress. The manifest is an audit trail, not authorization by itself.

## Role Decision Checkpoint

For every role, show the canonical company, title, job ID, URL, freshness evidence, work model/location, sponsorship evidence or `UNKNOWN`, hard-gate result, meaningful match score, priority score, matched evidence, gaps, and recommendation. Record only the exact selected job IDs in the approval scope.

## Resume Checkpoint

Generate a new non-overwriting resume version for every approved role. Show the PDF path, source/base lineage, change summary, two-page result, text extraction result, render inspection result, and verified links. Approval applies only to the displayed file hash or version identifier.

## Submission Checkpoint

Show the job, resume version, account/email to be used, all application answers, legally significant confirmations, and the exact final action. Record employer confirmation evidence after execution. If the site response is ambiguous, retain an unconfirmed state and do not retry automatically.

## Outreach Checkpoint

The order is recruiters, hiring managers, then other relevant professionals. For each outreach item, show recipient, current employer/title evidence, connection degree when visible, channel, role/job ID, subject when applicable, and exact text. A message may say the candidate applied only when the tracker shows a confirmed submission for that job.

Email addresses must be user-provided or directly verified from a reliable professional/public source. Search patterns, guessed corporate formats, and third-party enrichment guesses do not count as verification.

## Completion Report

Summarize the two or three companies, roles discovered/unique/active/eligible, gate failures, resumes generated and approved, applications prepared/submitted/blocked, LinkedIn requests/messages sent, emails sent, responses, follow-ups, and the next recommended batch. Do not modify either skill automatically based on results.
