# Target Company Job Campaign Design

## Objective

Add a separately selectable Codex skill, `target-company-job-campaign`, to this repository. One invocation should coordinate a focused campaign across two or three companies while reusing the existing private candidate profile, base resumes, preferences, trackers, application answers, and resume tooling.

## Selected Architecture

The new skill is an orchestrator, not a duplicate pipeline. It delegates evidence management, job gating and scoring, resume generation, application preparation, outreach preparation, and reporting to the installed `linkedin-job-search-pipeline` skill and its shared external workspace. Candidate data remains outside both installed skill packages and outside Git.

Each run creates a dated batch under `data/target-campaigns/<batch-id>/`. The batch manifest records the selected companies, lifecycle state, role decisions, approval checkpoints, and artifact locations. Existing normalized company, job, contact, and application CSV trackers remain authoritative.

## Workflow

1. Confirm the campaign belongs to the candidate represented by the shared workspace.
2. Select or recommend two or three companies using the stored strategy and current constraints.
3. Discover fresh roles, capture complete evidence, deduplicate, verify activity, apply hard gates, calculate meaningful relevance, score, and rank.
4. Present eligible roles and stop at the role-selection checkpoint.
5. For approved roles, create truthful two-page `SuryaResume.pdf` files using the owner reference workflow, run text/render/link QA, and stop at the resume checkpoint.
6. Prepare applications, reconfirm missing or legally significant fields, show the final payload, and stop at the submission checkpoint.
7. Submit only the exact applications approved by the user.
8. Identify recruiters first and hiring managers second. Draft role-specific LinkedIn outreach and email only when a professional address is verified from a reliable source.
9. Show exact recipients and text, stop at the outreach checkpoint, then send only approved items.
10. Update trackers and generate the campaign report.

## Approval and Safety Model

Research and local preparation may proceed autonomously. Role selection, resume acceptance, application submission, and external outreach require explicit approval at the point of action. Prior approval does not authorize changed recipients, text, answers, or job submissions. Authentication, CAPTCHA, rate limits, platform controls, and legally significant unknowns are never bypassed.

## Installation

The repository installer deploys both skills from one clone. The primary skill retains the scripts and shared references. The orchestrator contains concise routing instructions and refers to the primary installed skill for operational details. Updating the repository upgrades both recognized installations and preserves timestamped backups.

## Testing

Offline tests verify batch creation, two-to-three-company validation, non-overwrite behavior, shared-workspace isolation, lifecycle transitions, dual-skill installation, and structural validation. Existing pipeline and PDF tests continue to run unchanged.
