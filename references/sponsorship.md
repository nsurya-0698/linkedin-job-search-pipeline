# Sponsorship and Work-Authorization Classification

Treat immigration and work-authorization answers as legally significant candidate data. Never infer them from citizenship, country of education, current employer, name, location, or past employment.

## Candidate State

The candidate profile must separately record:

- country or countries in which the candidate is authorized to work;
- current authorization type, only if the candidate supplied it;
- expiration or future sponsorship need, only if supplied;
- whether employer sponsorship is required now or later;
- date and source of the candidate's confirmation.

If any required item is missing, use `CANDIDATE_STATUS_UNKNOWN` and ask before answering an application question.

## Job State

Classify each job using current, attributable evidence:

- `COMPATIBLE`: the posting or an authoritative company source explicitly supports the candidate's confirmed situation.
- `INCOMPATIBLE`: the posting explicitly rules out the candidate's confirmed situation.
- `UNKNOWN`: no usable statement is present.
- `REQUIRES_CONFIRMATION`: wording is conditional, internally inconsistent, outdated, or sourced from a non-authoritative page.

Record the quoted or closely paraphrased evidence, source URL, source type, and verification date. Prefer the current official job posting. Company-wide policy pages and recruiter statements can add context but should not silently override job-specific language.

## Hard-Rejection Evidence

If the candidate has confirmed that sponsorship is required, treat explicit language such as the following as incompatible:

- no or unavailable visa sponsorship;
- will not or cannot sponsor for this position;
- unrestricted or permanent work authorization required without current or future sponsorship;
- a named authorization/clearance condition the candidate has confirmed they do not meet.

Paraphrase the evidence in the tracker. Do not copy long passages from a posting.

Absence of sponsorship language is `UNKNOWN`, not rejection and not proof of compatibility. “Must be authorized to work” alone is not necessarily equivalent to “no sponsorship”; preserve the exact wording and seek clarification when it matters.

## Decision Matrix

| Candidate state | Job state | Result |
|---|---|---|
| sponsorship required | incompatible | hard reject |
| sponsorship required | compatible | pass sponsorship gate |
| sponsorship required | unknown/needs confirmation | continue research, flag before application |
| sponsorship not required | restriction satisfied | pass sponsorship gate |
| sponsorship not required | restriction not satisfied | hard reject |
| candidate status unknown | any material restriction | `NEEDS_INFORMATION` before application |

Never answer “yes” or “no” to work-authorization, sponsorship, export-control, citizenship, clearance, or relocation questions from inference. Draft the question and wait for the candidate's exact answer.

Reverify sponsorship evidence before preparing an older application and immediately before submission if the posting changed.
