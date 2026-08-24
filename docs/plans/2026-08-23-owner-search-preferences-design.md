# Owner Search Preferences Design

## Goal

Make the repository owner's approved search constraints portable across laptops without publishing the source resume or detailed employment record.

## Design

- Add a small, explicit owner-preferences reference containing only authorized search constraints.
- Route the skill to that reference when the campaign belongs to the repository owner; initialize a different candidate from their own answers rather than inheriting Surya's preferences.
- Keep candidate facts used for resume chronology, titles, project status, and education in the external campaign workspace.
- Preserve the existing hard gates, evidence requirements, and exact-action approval boundary.

## Published defaults

- H-1B sponsorship is required now or later.
- Remote is preferred; hybrid and onsite roles in any U.S. location are acceptable.
- Amazon is excluded from the current search.
- Roles explicitly requiring more than five years are rejected.
- Networking order is recruiters, hiring managers, then other relevant professionals.

## Validation

Run the offline test suite, validate the skill structure, rebuild `skill.zip`, inspect the archive contents, update the installed copy, and verify that private campaign files remain absent from Git.
