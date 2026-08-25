# Oracle Networking Credential Design

## Goal

Make Surya Teja Nammi's current employment at Oracle a prominent, truthful credential in every future LinkedIn connection request while preserving recipient-specific personalization, platform limits, and approval controls.

## Design

- Apply this behavior only after confirming the candidate is Surya Teja Nammi or explicitly adopts the owner defaults.
- Every first-contact LinkedIn connection note must state near the beginning that Surya currently works at Oracle.
- Prefer the verified public title from the runtime candidate profile when space permits; otherwise state only the verified employer fact.
- Give the Oracle credential high drafting weight, but keep a distinct recipient-specific reason for connecting.
- Never invent an Oracle team, tenure, project, achievement, or title. If current employment becomes unresolved or stale, stop and reconfirm it before sending.
- Keep each note within the platform limit and preserve exact-message approval before transmission.

## Components

- `SKILL.md`: core owner-specific outreach invariant.
- `references/networking.md`: drafting and QA requirements.
- `references/owner-preferences.md`: owner-specific Oracle preference and evidence boundary.
- `README.md`: portable behavior summary.
- `tests/test_pipeline.py`: regression checks for the portable contract.

## Validation

Run the skill validator and repository test suite, then sync the validated repository tree to the installed skill copy. Commit and push only after both copies match.
