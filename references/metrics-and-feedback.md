# Metrics, Dashboards, and Feedback

The primary KPI chain is:

`qualified applications -> recruiter responses -> interviews -> final rounds -> offers`

Raw applications and connections are supporting counts, not success metrics.

## Funnel Definitions

Report consistent, deduplicated counts.

### Jobs

- discovered jobs;
- unique jobs after deduplication;
- active and stale jobs;
- hard rejections by sponsorship, experience, location, core qualification, role mismatch, and inactive status;
- jobs below 50% relevance;
- eligible and high-priority jobs;
- applications prepared, approved, and submitted.

### Networking

- contacts discovered by category;
- connection/message drafts;
- approved and sent outreach;
- responses, conversations, and referrals;
- overdue and completed follow-ups.

### Interviews

- recruiter responses and screens;
- hiring-manager screens;
- technical interviews;
- onsite/panel and final rounds;
- employer rejections, withdrawals, and offers.

Calculate a conversion only when the denominator is nonzero and the underlying states are comparable. Show numerator, denominator, percentage, and reporting window. Do not compare a newly submitted cohort with mature applications without labeling the lag.

## Command-Center Output

The dashboard should show:

- Top 10 and next-best jobs;
- new high-priority opportunities;
- stale jobs and sponsorship items needing verification;
- applications awaiting approval;
- recruiters, hiring managers, and other contacts to consider;
- follow-ups due;
- upcoming interviews and preparation gaps;
- company application history;
- key counts and conversion rates;
- the current bottleneck and evidence supporting it.

Use specific bottleneck language, for example: “Qualified application volume is healthy, but recruiter-response conversion is low for applications older than 14 days.” Do not diagnose a bottleneck from a tiny or immature sample without saying so.

## Bottleneck Heuristics

Consider, then validate with the actual campaign:

- low eligible-job volume: search strategy, constraints, or source coverage;
- many hard rejections: poorly targeted queries or unresolved candidate constraints;
- many prepared but few approved: review burden or unclear prioritization;
- many applications but low recruiter response: targeting, resume evidence, company mix, or sponsorship uncertainty;
- recruiter screens but few technical rounds: positioning or screen preparation;
- technical rounds but few finals: technical/system-design gaps;
- finals but no offers: late-stage role fit, depth, communication, or sample size.

## End-of-Session Report

For each major session summarize:

1. jobs found, unique, fresh, rejected, recommended, prepared, awaiting approval, and submitted;
2. contacts by category, drafts, approved outreach, responses, and follow-ups;
3. resumes generated, versions, meaningful changes, repeated JD themes, and evidence gaps;
4. company additions, application history, duplicates avoided, and strong opportunities;
5. interviews, likely topics, outcomes, and preparation gaps;
6. data-quality problems and tool limitations;
7. next highest-value actions.

## Learning Without Silent Skill Changes

Update runtime search strategy and trackers when outcomes supply meaningful evidence. Preserve raw state and version IDs so later A/B testing is possible, but do not implement A/B assignment in version one.

At the end of a major campaign, propose skill improvements covering what worked, failures, data quality, sponsorship verification, resume tailoring, search, networking, trackers, automation opportunities, candidate-data gaps, and tool limitations. Do not modify the skill until the user approves the proposed change.
