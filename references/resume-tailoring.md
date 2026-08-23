# Truthful Resume Tailoring and PDF QA

Tailor only after the job is active, deduplicated, hard-gate eligible, at least 50% meaningfully relevant, and selected by the user for preparation.

## Preserve the Base

- Treat every supplied base resume as read-only evidence.
- Record its filename, SHA-256 hash, extraction date, and unresolved conflicts.
- Never replace, rename, or edit the base file.
- Create a new version only for meaningful job-specific changes.
- Never overwrite a tailored version.

Use a stable filename such as `company-role-jobid-v1.pdf`, with lowercase filesystem-safe tokens. Increment the version only when content meaningfully changes.

## Build a Tailoring Plan

Identify the five to ten most important JD requirements. For each proposed edit record:

| Field | Requirement |
|---|---|
| Section/bullet | The exact resume element affected |
| Change | Before and after wording or the reordering action |
| Reason | Why this helps the reader evaluate the requirement |
| JD requirement | The requirement addressed |
| Source evidence | Base-resume/profile evidence proving the revised claim |
| Risk | Ambiguity, metric, date, title, or technology that needs confirmation |

Allowed changes include reordering existing bullets, choosing the most relevant supported bullets, clarifying wording without changing meaning, adjusting summary emphasis, and reordering documented skills.

Do not add projects, technologies, responsibilities, metrics, certifications, dates, titles, seniority, leadership, or accomplishments without source evidence. Do not transform exposure into production ownership or adjacent experience into direct expertise. Do not keyword-stuff.

When two base sources conflict, omit the disputed fact or ask the user to resolve it before generating a version that depends on it.

## Structured Generation Input

The PDF generator is a renderer, not an author. Give it approved structured content containing:

- contact fields chosen for this application;
- summary;
- skills grouped by category;
- experience entries with employer, title, location, dates, and approved bullets;
- education and certifications;
- metadata: base hash, job ID, JD hash, version ID, and change log.

Keep personal fields out of logs and public fixtures. Do not include a photo, columns, graphics, skill bars, or text boxes in an ATS resume.

## PDF Requirements

Produce a selectable-text, letter-size PDF with consistent typography, clear headings, readable bullets, predictable margins, and no unnecessary decoration. Prefer one or two pages according to the candidate's evidence; never shrink text to conceal poor prioritization.

Before delivery:

1. reopen the generated PDF;
2. verify expected page count and metadata;
3. extract text and confirm all required sections, dates, contact fields, and bullet content are present;
4. render every page to an image;
5. inspect every page for clipping, overlap, broken glyphs, orphaned headings, inconsistent spacing, or accidental blank pages;
6. compare generated claims against the approved tailoring plan;
7. run `resume_qa.py` and treat a nonzero exit as a blocker.

If visual rendering is unavailable, do not claim visual QA passed. Report the missing dependency and keep the version in a draft state.

## Version Metadata

For every generated resume preserve:

- version ID and prior version, if any;
- base resume hash;
- job ID and canonical URL;
- JD hash and verification timestamp;
- generated timestamp;
- change summary and reason for each change;
- source evidence;
- PDF QA result and tool versions.

Do not regenerate solely to change a timestamp. Preserve prior versions and their metadata for campaign history unless the user requests deletion or sets a retention policy, so application outcomes remain attributable without imposing indefinite retention.
