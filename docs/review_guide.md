# Review guide

Human approval is performed through protected GitHub pull requests. The CLI has
no reviewer login, user directory, role assignment, access-policy file, or
review-decision command.

Record statuses remain `needs_revision`, `accepted`, and `rejected`, but these
are lifecycle labels rather than authenticated reviewer events. GitHub is the
authoritative source for reviewer identity, approval, requested changes, and
history.

Before requesting review:

1. Run the deterministic schema, registry, execution, duplicate, and provenance
   checks that apply to the change.
2. Run the production OpenAI quality judge when the production workflow
   requires it. Model evidence informs the reviewer but never counts as human
   approval.
3. Keep incomplete records at `needs_revision`. An `accepted` record must have
   no validation stage marked `failed` or `not_run`.
4. Open a pull request using the repository template and include the generated
   quality report when applicable.

The PR reviewer checks natural Turkish, realistic localization, category and
tool choice, arguments, call/result linkage, execution evidence, grounding,
provenance, licensing, duplicates, safety, and side effects. Requested changes
are made on the same branch so GitHub retains the complete discussion.

Recommended `main` branch protection:

- require a pull request before merging;
- require at least one approval;
- dismiss stale approvals when new commits are pushed;
- require the `validate` status check and an up-to-date branch;
- block force pushes and deletion.

High-risk, stateful, multi-tool, or license-sensitive changes can request an
additional reviewer in the PR without introducing application-level roles.
CODEOWNERS may be added later when stable GitHub usernames are known.
