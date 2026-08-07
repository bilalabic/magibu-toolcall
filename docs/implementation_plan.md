# Staged implementation plan

This plan implements infrastructure only. It does not run the 20–30-example
pilot or any production-sized dataset/benchmark activity.

| Stage | Objective and files | Validation gate |
|---|---|---|
| 1 | Assessment, architecture, plan, traceability, risks, dependencies, deferred decisions (`docs/`) | Documents exist and explicitly separate current/deferred work |
| 2 | Package/config/logging/CLI/test skeleton (`pyproject.toml`, `src/`, `tests/`, `.env.example`) | Package import, CLI help, and test discovery pass |
| 3 | Four Draft 2020-12 schemas plus valid/invalid fixtures (`schemas/`, `tests/fixtures/`) | Schema self-check and fixture tests pass |
| 4 | Registry record loader/lookups/duplicates/demo fixtures (`registry/`, `src/.../registry.py`) | Registry unit and CLI validation tests pass |
| 5 | ID and version utilities (`ids.py`, `versioning.py`) | Prefix, range, collision, stability, and SemVer tests pass |
| 6 | Layered deterministic validator (`validation/`) | Required diagnostic, flow, execution, benchmark, and review cases pass |
| 7 | Execution protocol and deterministic adapters (`execution/`) | Mode/status/normalization/fallback/reset tests pass |
| 8 | Blueprint workflow and one fixture per main category (`blueprints/`) | Schema, priority, and candidate-hook tests pass |
| 9 | Provenance/deduplication (`provenance.py`, `deduplication.py`) | Hash/fingerprint/report/test-double tests pass |
| 10 | Final response/provider boundaries (`generation/`) | Applicability, default, failure, and conflict-hook tests pass |
| 11 | Benchmark evaluator/run separation (`evaluation/`) | Selection/arguments/no-tool/clarification/parallel/sequential tests pass |
| 12 | Review and export (`review/`) | transitions, roles, self-review, accepted-only export tests pass |
| 13 | Minimal end-to-end fixture (`tests/integration/`) | Complete deterministic flow passes |
| 14 | Contributor and handover docs (`README.md`, `docs/`) | Full suite and documented CLI smoke tests pass |
| 15 | Parallel dataset/benchmark lifecycles (`cli.py`, `contamination.py`, `freeze.py`, `reporting.py`, `data/dataset`, `data/benchmark`) | Namespace-only CLI, cross-corpus contamination, freeze verification, and isolated run/report tests pass |
| 16 | Source ingestion and localization (`sources.py`, `localization.py`, source-work-item schema) | Actual xLAM/When2Call shapes, JSON-string fields, provenance, machine-field preservation, and localization patch tests pass |
| 17 | Production providers and integrations (`network.py`, `generation/providers.py`, `semantic.py`, `execution/http_api.py`) | Injected-transport tests prove request/response parsing, secret redaction, embedding cache/cosine behavior, HTTPS/read-only enforcement, and normalized API statuses without live calls |
| 18 | Reviewer access and scalable jobs (`access.py`, `batch.py`, access/job schemas, CLI) | Active principal, role/scope/permission, benchmark isolation, shard/checkpoint/resume, collision, and failure-queue tests pass |
| 19 | Production CLI and handover (`cli.py`, Turkish README files, architecture/traceability docs) | Source import/localization, batch plan/status, semantic provider selection, policy-gated review/export/freeze/run, full suite, and deterministic end-to-end tests pass |
| 20 | Quality-first normal dataset generation (`dataset_workflow.py`, dataset CLI) | Blueprint preflight, active-source restriction, automatic paths/IDs/distributions, provider-claim sanitization, advanced resume, and full-suite tests pass |
| 21 | Evidence-backed dataset quality and computed review (`quality.py`, review schema/CLI) | Declared-mode execution, result comparison, deterministic/semantic duplicate gates, durable reports, reviewer decisions, computed acceptance, and full-suite tests pass |

Each stage is implemented as the smallest complete slice, tested before the next
stage, and reflected in the traceability matrix. Failures are fixed or recorded;
no failed gate is silently skipped.

## Completion

All 21 infrastructure stages completed by 2026-08-07. Stages 16-19 add the
production-operation foundation requested after the initial handover. They do
not authorize or perform bulk dataset/benchmark production, gated dataset
download, live provider spend, or final Turkish API selection.

Stage 20 narrows the active workflow to original Turkish and Türkiye-native
dataset generation. It automates routine job mechanics without bypassing
manifest, provenance, access, validation, review, or audit gates. Translation
and benchmark operations are retained but operationally paused.

Stage 21 adds an explicit quality boundary between generation and human review.
Automatic checks produce evidence and update only the gates they actually ran;
reviewer decisions are persisted separately and overall acceptance is computed
from completed gates and required perspectives.
