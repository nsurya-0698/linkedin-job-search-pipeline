# Search Strategy

Keep this file as immutable campaign methodology. Store the candidate-specific, evolving search plan in the campaign workspace so learning does not rewrite the installed skill.

## Derive Role Families from Evidence

Start with the candidate's strongest repeated capabilities, business domains, scope, and accomplishments. Map those to role families and adjacent titles; do not begin with a generic title list.

For each role family, maintain:

- supported titles and title variants;
- core responsibilities supported by the resume;
- strongest technologies and domains;
- adjacent responsibilities that require a transferability explanation;
- exclusions and hard constraints;
- seniority range supported by evidence;
- search strings and company-career keywords;
- results and interview signals observed to date.

Do not infer a target role merely because it appears aspirational or popular.

## Initial Company and Work-Model Priority

Use this ordering unless the user changes it:

1. remote + strong product company + strong match;
2. remote + strong engineering company + good match;
3. hybrid + strong product company + strong match;
4. other suitable roles.

Initially favor large product-based technology companies and product-driven organizations with substantial engineering teams. Consider a smaller company when the role is exceptionally aligned, the product and team are credible, or the user changes the strategy.

Store company type, product/engineering classification, priority, remote availability, relevant job families, current sponsorship evidence, applications, recruiters, hiring managers, contacts, and outcomes. Company reputation does not compensate for a poor role match.

## Discovery Record

Capture enough source material to reproduce the decision:

- platform and platform job ID;
- canonical job or requisition ID;
- company, title, seniority, location, work model, and employment type;
- canonical and alternate URLs;
- complete JD or a permitted local snapshot;
- required and preferred qualifications;
- responsibilities and technologies;
- experience language;
- sponsorship/work-authorization language;
- deadline when available;
- `first_seen`, `last_verified`, `job_status`, `job_active`, and `jd_changed`;
- JD hash and source timestamp.

Prefer the current official company posting when verifying active status and requirements. Use LinkedIn as a discovery source without assuming its copy is the newest.

## Deduplication and Freshness

Deduplicate before scoring using, in descending confidence:

1. exact platform job/requisition ID;
2. normalized canonical URL;
3. explicit same requisition across sources;
4. normalized company + title + location;
5. high JD similarity reviewed with dates and team/location differences.

Retain a canonical row and alternate-source evidence. Similar titles in different teams or locations are not automatically duplicates.

Reverify a job before tailoring when its verification is older than three days, and always immediately before submission. Treat removed application controls, a closed status, a materially changed JD, or an official replacement requisition as stale until re-evaluated. Do not treat an accessible old URL as proof the job is active.

## Initial 50-Role Campaign

Build a ranked queue rather than accepting the first 50 results:

- Top 10: highest interview potential and cleanest constraints;
- Next 20: solid eligible roles worth structured preparation;
- Backup 20: eligible but lower priority, uncertain, or awaiting verification.

The campaign pipeline is:

`Discover -> Deduplicate -> Verify -> Hard gate -> Match -> Score -> Rank -> Prepare -> Approve`

Apply the explicit maximum of five years required experience, sponsorship compatibility rules, and 50% meaningful-alignment gate before allocating resume-tailoring effort.

## Weekly Adaptation

At least weekly, compare search mix with recruiter-response and interview outcomes. Update the runtime strategy—not this reference—with:

- titles and queries producing qualified jobs;
- recurring false positives and exclusions;
- companies and teams producing responses;
- repeated missing qualifications;
- remote/hybrid availability changes;
- sponsorship evidence quality;
- role families that are over- or under-sampled;
- the current funnel bottleneck.

Do not overfit to a single rejection. Require a recurring pattern or a material new candidate constraint before changing the strategy.
