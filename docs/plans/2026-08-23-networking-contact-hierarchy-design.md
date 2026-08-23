# Networking Contact Hierarchy Design

## Goal

Make every networking campaign select relevant recruiters before hiring managers and select other professional contacts only after both higher tiers are exhausted.

## Selection model

Use a strict three-tier hierarchy:

1. Recruiters: corporate, technical, agency, staffing, talent-acquisition, and sourcing professionals.
2. Hiring managers: confirmed or strongly evidenced managers for the relevant role, team, or job family.
3. Other relevant professionals: engineering leaders, engineers, and employees with genuine technical or company overlap.

Eligibility remains a prerequisite. A recruiter without credible job, company, role-family, or geographic relevance does not outrank a relevant lower-tier contact. Within a tier, rank candidates by target-job and company relevance, hiring evidence, mutual context, and truthful personalization quality.

## Batch behavior

Fill each outreach batch from the highest available tier. Move to the next tier only when there are not enough eligible candidates in the higher tier. When a lower-tier contact is included, record why the higher tiers were insufficient. Keep all existing approval, personalization, truthfulness, platform-limit, and anti-automation controls.

## Implementation and verification

Add the invariant to the skill entrypoint and networking reference, surface it in the repository README, and document it in the implementation report. Add regression checks that exercise tier classification and ordering rather than merely matching prose. Rebuild `skill.zip`, run the complete offline tests and skill validator, update the installed copy through the supported setup flow, and commit the repository changes.
