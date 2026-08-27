# Reference-Matched Resume Workflow Design

## Goal

Generate polished, job-specific two-page PDF resumes that preserve Surya's approved reference format while changing only evidence-backed summary, skills, and experience bullets.

## Output contract

- Every portal upload is named `SuryaResume.pdf`.
- Store each application artifact at `YYYY-MM-DD/<company>/<job-id>-<role>/SuryaResume.pdf`.
- Keep job metadata and the tailoring evidence log beside the PDF.
- Use the supplied `suryaReume.pdf` as the canonical visual and structural reference.

## Resume contract

- Produce exactly two balanced, substantially filled US Letter pages.
- Preserve the reference section order, typography hierarchy, right-aligned dates, company/location lines, spacing, bullets, and education treatment.
- Require a concise professional summary tailored to the job.
- Tailor the summary, skill ordering/content, and experience bullet selection/order/wording substantially enough to match the role.
- Every changed claim must remain supported by the evidence ledger; do not add unsupported technologies, metrics, ownership, titles, dates, or production claims.
- Preserve clickable LinkedIn, Portfolio, and certification links with readable labels.

## Workflow

1. Verify and score the active posting.
2. Create the dated company/job folder.
3. Extract the most important responsibilities and qualifications.
4. Map each requirement to candidate evidence.
5. Build the tailored summary, skills, and bullet plan.
6. Render `SuryaResume.pdf` from the reference-matched template.
7. Validate two-page count, selectable ATS text, required content, hyperlinks, and absence of unsupported claims.
8. Render and visually inspect both pages for clipping, whitespace balance, hierarchy, and complete page use.
9. Preserve metadata and never submit until the application-specific approval requirements are satisfied.

## Repository and portability

Store the reference PDF and reusable template assets in the skill repository so a cloned installation can reproduce the workflow. Runtime application folders remain outside the installed skill by default. Include a clear README example showing installation, initialization, and the output convention.

## Testing

- Unit-test folder naming and stable upload filenames.
- Generate a fixture resume and require exactly two pages.
- Check selectable text, required sections, summary presence, and link annotations.
- Run the existing pipeline test suite and skill validator.
- Rebuild and visually inspect both pages of every requested resume.
