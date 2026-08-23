# Job Scoring and Decision Gates

Use this reference after deduplication and freshness verification. A score ranks an eligible role; it must never override a hard rejection.

## 1. Build the Evidence Table

For every material JD requirement, record:

| Field | Meaning |
|---|---|
| Requirement | A concise paraphrase of the JD language |
| Kind | Core responsibility, required skill, preferred skill, seniority, domain, education, location, or work authorization |
| Importance | `critical`, `high`, `medium`, or `low` |
| Candidate evidence | Exact resume/profile role, project, skill, or accomplishment supporting the match |
| Match | `MATCH`, `PARTIAL`, `ADJACENT`, `MISSING`, or `UNKNOWN` |
| Source | Base resume/profile section and version |
| Notes | Transferability, ambiguity, or evidence that must be confirmed |

Do not award a match because the same word appears in both documents. A `MATCH` requires demonstrated use or a clearly supported capability. `PARTIAL` or `ADJACENT` requires an explicit explanation of transferability.

## 2. Apply Hard Gates First

Return `DO_NOT_APPLY` with the exact evidence when any condition is true:

- the posting is closed, removed, or expired;
- the candidate requires sponsorship and the current posting explicitly rules it out;
- an explicit minimum experience requirement is greater than five years;
- a location, travel, clearance, licensure, schedule, or employment-type requirement is impossible;
- one or more truly core required qualifications are absent;
- the work is fundamentally outside the candidate's evidence-backed job families.

Do not hard reject when experience, sponsorship, or another item is not stated. Mark it `UNKNOWN` and identify a verification step. A title containing “Senior” is not itself an experience gate.

A materially changed JD invalidates the old evaluation and blocks preparation with `NEEDS_INFORMATION` until the current JD is re-evaluated. Do not reject solely because it changed; apply gates and scores to the new content.

## 3. Calculate Meaningful Relevance

Assign requirement weights by importance:

- critical: 5
- high: 3
- medium: 2
- low: 1

Assign match credit:

- `MATCH`: 1.0
- `PARTIAL`: 0.6
- `ADJACENT`: 0.35
- `MISSING`: 0
- `UNKNOWN`: exclude from the denominator only when the JD itself is ambiguous; otherwise treat as 0

Calculate:

`meaningful_relevance = credited_weight / evaluable_weight * 100`

Required/core responsibilities and skills must contribute at least 70% of the evaluable weight. Preferred qualifications may refine the score but may not dominate eligibility.

Interpretation:

- below 50%: `DO_NOT_APPLY`
- 50-59%: eligible for priority scoring with a `BORDERLINE_RELEVANCE` flag
- 60% or above: eligible for priority scoring

The 50% gate is necessary, not sufficient.

## 4. Calculate the Priority Score

For an eligible job, score these dimensions to a maximum of 100:

| Dimension | Points | Decision basis |
|---|---:|---|
| Core responsibility alignment | 25 | Direct evidence for the work performed day to day |
| Required technical alignment | 20 | Demonstrated depth in required technologies or defensible equivalents |
| Experience and seniority alignment | 15 | Scope, years, ownership, and level without title inflation |
| Domain/platform evidence | 10 | Relevant AI, backend, cloud, distributed systems, platform, or industry experience |
| Work model and location | 10 | Remote-first preference and practical location fit |
| Company/product priority | 8 | Product focus, engineering relevance, and current campaign tier |
| Sponsorship confidence | 7 | 7 compatible; 3 unknown/needs verification; incompatible is a hard rejection |
| Interview story strength | 5 | Specific source-backed accomplishments likely to support a convincing interview |

Use proportional points; do not round every dimension up. Record a one-sentence rationale for each dimension.

Priority categories:

- 90-100: `TOP_PRIORITY`
- 75-89: `HIGH_PRIORITY`
- 60-74: `GOOD`
- 50-59: `BORDERLINE`
- below 50: `DO_NOT_APPLY`

A job that barely passes meaningful relevance can still score below 50 after location, company, sponsorship uncertainty, or weak interview evidence is considered.

## 5. Map Scores to the Final Decision

Apply this precedence; the first matching row wins:

| Condition | Decision |
|---|---|
| hard gate rejects, meaningful relevance is below 50%, or priority score is below 50 | `DO_NOT_APPLY` |
| freshness/material-change review is unresolved, a reversible candidate unknown could change eligibility, or a required score is unavailable | `NEEDS_INFORMATION` |
| relevance is 50-59% or priority score is 50-59 | `BORDERLINE` |
| hard gate passes, relevance is at least 60%, priority score is at least 60, and no decision-changing unknown remains | `APPLY` |

An `APPLY` decision authorizes consideration and preparation only; it does not authorize submission.

## 6. Handle Uncertainty

Use `NEEDS_INFORMATION` when a missing candidate fact could reverse the decision, especially work authorization, relocation, clearance, compensation, or conflicting employment dates. Do not convert uncertainty into a favorable assumption.

Store:

- decision timestamp;
- JD hash and canonical URL;
- base resume/profile version;
- gate outcomes;
- meaningful relevance;
- dimension scores;
- exact rejection or uncertainty reason;
- analyst notes and next verification action.

Re-score when the JD, candidate source of truth, or a material constraint changes. Before replacing a material decision, record the prior JD hash, relevance/priority scores, decision, timestamp, and reason in the job notes or a dated campaign report so the change is not silent.
