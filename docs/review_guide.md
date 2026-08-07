# Review guide

Statuses are `needs_revision`, `accepted`, and `rejected`. Every event records
reviewer ID, perspective (`language` or `technical`), previous/new status, notes,
and timestamp.

Language review checks natural Turkish, realistic expression, inflection,
localization, repetition, and whether the final answer completes the request.
Technical review checks category priority, tool choice, schemas, arguments,
call/result linkage, execution evidence, grounding, provenance, and duplicates.

A contributor cannot provide final approval for their own record. Multi-tool,
sequential, and explicitly marked records require two distinct reviewers and
both perspectives. Production sampling rules (including the later 20–25% second
review sample) remain a team decision. An accepted record with deterministic
errors or incomplete validation is blocked at export.

Production CLI review/export/freeze/run operations require an access-policy
principal. The principal must be active, scoped to the lifecycle, hold the
required permission, and hold the reviewer role matching the declared review
perspective. Dataset and benchmark team membership can be mutually exclusive.
Authorization decisions are appended to a SHA-256 hash-chained audit JSONL. This
application policy complements rather than replaces filesystem/storage ACLs.
