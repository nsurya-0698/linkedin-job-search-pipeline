# Application Preparation and Approval Workflow

Separate eligibility screening from employer outcomes. Do not use one `REJECTED` state for both.

## State Model

Recommended states:

1. `DISCOVERED`
2. `EVALUATED`
3. `SCREENED_OUT` — the pipeline decided not to apply; store the gate/relevance reason
4. `READY`
5. `AWAITING_APPROVAL`
6. `APPROVED`
7. `APPLIED`
8. `RECRUITER_CONTACTED`
9. `SCREEN`
10. `TECHNICAL`
11. `ONSITE`
12. `FINAL`
13. `OFFER`
14. `EMPLOYER_REJECTED`
15. `WITHDRAWN`
16. `CLOSED_OR_EXPIRED`

Reject invalid transitions. Preserve the dedicated stage dates and add notes for intentional non-linear corrections or material context. If the workspace adds an append-only event log later, record every transition there. A duplicate job points to a canonical job and must never create a second application.

## Preparation Packet

For an eligible, user-selected job, prepare:

- canonical job record and current JD hash;
- decision evidence, relevance, score, and sponsorship classification;
- tailored resume version and QA record;
- candidate contact fields;
- application fields and source for each answer;
- screening questions with draft answers;
- work authorization/sponsorship questions marked for confirmation;
- compensation response only if candidate requirements are recorded;
- recruiter/hiring-manager context and approved outreach draft, if relevant;
- follow-up date and notes.

Never guess a missing field. Mark it `NEEDS_CANDIDATE_INPUT` and explain why it matters.

## Approval Boundary

Preparation mode may write local files and trackers. It may not:

- click a final application submission control;
- send a LinkedIn connection request or message;
- send email or a recruiter form;
- accept legal attestations;
- agree to relocation, compensation, work authorization, background-check, export-control, or demographic answers for the user.

Immediately before an external action, show the destination, job/contact, resume version, message or material answers, and any sensitive data that would be transmitted. Obtain explicit approval for that action. A prior approval for research or drafting does not authorize submission.

After an approved action, verify the observable success state once and record the timestamp and evidence. Do not repeatedly submit if the result is ambiguous. Retain the prior state (normally `APPROVED`), add `SUBMISSION_UNCONFIRMED` with context to notes, and surface the manual verification step.

## Freshness and Company History

Immediately before approval:

1. verify the posting remains active;
2. compare the current JD hash to the evaluated hash;
3. recheck sponsorship language;
4. review active and recent applications at the same company;
5. confirm the resume version matches the current job record;
6. refresh missing candidate answers.

Do not block a distinct team or role merely because another application exists, but surface the company history and avoid blind repetitive submissions.

## Follow-Up

Set a deliberate follow-up date when the application or outreach is recorded. A follow-up draft must reference only real context. Stop outreach after a clear decline, opt-out, or platform limit, and update the contact/application record.
