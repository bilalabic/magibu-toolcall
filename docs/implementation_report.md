# Infrastructure implementation report

Report date: 2026-08-06

## 1. Repository assessment

The workspace was empty: no Git metadata, architecture, dependencies, schemas,
scripts, conventions, tests, or documentation existed. Nothing was overwritten
or reused. The implementation follows the brief's Python 3.11+, JSONL, JSON
Schema Draft 2020-12, `jsonschema`, `pytest`, environment configuration, and
structured-logging direction. New Turkish fixture text is UTF-8; mojibake shown
in the attachment was not copied.

Important conservative choices are documented in `repository_assessment.md`.
The principal ambiguity resolved was to represent parallel calls in one
assistant message and sequential calls in separate assistant messages with each
prior result before the next call.

## 2. Architecture summary

The architecture is a standard-library-first Python package. JSON Schema owns
structural rules. Layered Python validation owns registry cross-references,
argument/result schemas, category priority, message order, execution/final
response applicability, benchmark decisions, and review consistency.

The deterministic flows are parallel and independent:

```text
shared registry/schema/category infrastructure
  -> dataset candidate -> automatic quality evidence -> human review
     -> accepted training data
  -> benchmark candidate -> benchmark review -> contamination gate
     -> frozen gold + checksum manifest -> isolated run logs
```

Dataset records remain under `data/dataset`; benchmark candidates and frozen gold
remain under `data/benchmark`; predictions and evaluation output belong under
`runs/<model_name>/<run_id>.jsonl`. Adapters route only to the
requested execution type. Quality reports preserve execution and duplicate
evidence. Review events distinguish reviewer decisions from computed overall
status, and accepted export revalidates records.

## 3. Implemented components

- Project/package/config/logging/CLI: `pyproject.toml`, `.env.example`,
  `configs/default.json`, `src/tool_call_tr/config.py`, `logging.py`, `cli.py`.
- Schemas: `schemas/common.schema.json`, `dataset.schema.json`,
  `benchmark.schema.json`, `tool_registry.schema.json`, and
  `scenario_blueprint.schema.json`, plus source-work-item, job-manifest, and
  access-policy schemas.
- Schema engine and diagnostics: `src/tool_call_tr/schemas/` and `validation/`.
- Registry and clearly marked demo fixtures: `src/tool_call_tr/registry.py`,
  `registry/registry.jsonl`, and `registry/fixtures/`.
- IDs/versioning: `ids.py` and `versioning.py`.
- Execution contracts/adapters/statuses/transition and transfer checks:
  `execution/core.py`, `execution/adapters.py`, and the HTTPS-only read-only JSON
  adapter in `execution/http_api.py`.
- Blueprint store, priority rules, and benchmark-draft hook: `blueprints.py`.
- Provenance and duplicate signals: `provenance.py` and `deduplication.py`.
- Actual xLAM/When2Call format adapters and machine-safe Turkish localization:
  `sources.py` and `localization.py`.
- Injectable JSON transport, DeepSeek structured generation, OpenAI embedding
  batches/cosine/cache: `network.py`, `generation/providers.py`, `semantic.py`.
- Checksum-bound resumable jobs with ID collision preflight, target distribution
  validation, streaming shards, atomic parts, checkpoints, and error queues:
  `batch.py` and the dataset/benchmark CLI namespaces.
- Active principals, role/scope/permission checks, dataset/benchmark team
  isolation, and hash-chained audit events: `access.py` and the access-policy
  gates in the CLI.
- Final-response methods, conflict/grounding hooks, provider protocols/mocks,
  retries, and configuration gates: `generation/`.
- Exact/five-point evaluation, category metrics, semantic hook, and isolated run
  writer: `evaluation/`.
- Dataset/benchmark CLI namespaces, cross-corpus contamination, benchmark gold
  freeze/verification, lifecycle reports, and generalized run orchestration:
  `cli.py`, `contamination.py`, `freeze.py`, `reporting.py`, and
  `evaluation/runner.py`.
- Review transitions and accepted-only export: `review.py`.
- Valid/invalid schema/category/evaluator fixtures and unit/integration tests:
  `tests/fixtures`, `tests/unit`, and `tests/integration`.
- Contributor, proposal, blueprint, validation, execution, review, versioning,
  risk, limitations, deferral, traceability, and next-stage documentation:
  `docs/`.

## 4. Deferred components

### Tool research

The final 12–20 tools, API/license/freshness research, stable fixtures, safety
approval, and registry promotion from `demo`/`candidate` are pending team
decisions. The generic real-API adapter is implemented; no particular Türkiye
API is thereby approved.

### 20–30-example pilot

Actual pilot blueprints/candidates, live provider configuration, production
semantic threshold/model approval, contributor ranges, reviewer assignments,
and pilot-driven schema/validator revisions are deferred. Dataset and benchmark
ownership, directories, CLI namespaces, policy scopes, batch manifests, and
contamination/freeze gates are structurally isolated; real staff assignments and
storage ACLs remain deferred.

### 250-example first stage

The 250 accepted dataset records, 100 gold benchmark records, source/category
distribution work, 12 approved tools, complete human review, and initial model
results were not produced.

### 1,000-example second stage

The 1,000 accepted records, 150–200 benchmark records, 300 Türkiye-native
records, production semantic deduplication/contamination runs, targeted
error-driven generation, final Dataset Card, and quality/error report are
deferred.

### Final benchmark evaluation

No live model was run and no benchmark result is claimed. Model selection,
versions, costs, output collection, semantic judging, and final reporting remain
future work.

## 5. Validation results

Final commands:

```text
.venv\Scripts\python.exe -m pytest
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
.venv\Scripts\python.exe -m compileall -q src
.venv\Scripts\python.exe -m pip check
```

The final suite passes 145 tests, including the original deterministic flow and
an independent parallel dataset/benchmark lifecycle flow. Added tests cover
actual xLAM/When2Call shapes, machine-safe localization, source terms gates,
DeepSeek/OpenAI request parsing, embedding cache/cosine behavior, HTTPS allowlist
and normalized statuses, access scopes/roles/permissions/audit tamper detection,
streaming shard plans, checksum/ID/distribution gates, interruption/resume,
failure queues, dataset/benchmark batch CLI flows, normal dataset job planning,
active-source enforcement, provider quality-claim sanitization, automatic
execution/result evidence, duplicate/semantic gate state, and computed reviewer
acceptance.
The verification script also validates all three registry JSONL records and the
complete dataset fixture. Compilation succeeds and pip reports no broken
requirements. Final failures: 0. Remaining warnings: 0.

Failures found and fixed during incremental development were: inaccessible
system pytest temp storage (moved into the workspace), argparse help expectation,
benchmark prompts incorrectly treated as completed dataset conversations,
empty output initially classified as invalid output, and Turkish uppercase `İ`
normalization. The lifecycle-separation change introduced no full-suite failure;
focused namespace/lifecycle tests passed before the final full-suite run. Legacy
flat CLI aliases were intentionally removed during `0.1.0` cleanup. No failure
was skipped.

Known limitations are listed in `known_limitations.md`; most notably, production
transports/adapters were tested without live credentials or network calls, no
final Türkiye-native tool is approved, and free-text semantic/Turkish judgment
still requires a provider plus humans.

## 6. Requirement traceability

Fully implemented infrastructure includes all schemas, fixtures, registry
lookups/duplicates, IDs/versions, deterministic validator diagnostics, local and
mock execution, explicit fallback policy, provenance/hashes/fingerprints,
benchmark scoring/metrics/run separation, review/export, CLI, and end-to-end
verification.

Production infrastructure now includes semantic embedding similarity,
DeepSeek structured generation, read-only real API execution, source import and
localization, access policy, and resumable scale controls. Partially implemented
by deliberate scope: free-text semantic/Turkish judging, state-changing external
sandboxes, and production final-answer generation. Execution of volume targets
and final publications is deferred. External decisions remain: approved
tools/licenses, model versions/thresholds, reviewer IDs, storage ACLs, and
budgets. The row-level matrix is in
`requirement_traceability.md`.

## 7. Next safe step

Before generating data, research and team-approve a small diverse tool subset,
freeze the next `0.1.x` registry revision, select provider models/thresholds,
create the real access-policy principal directory plus storage ACLs, then author
and validate a small `original_turkish`/`turkey_native` blueprint pilot. Run the
pilot through generation, automatic quality reports, and real reviewer decisions
before increasing volume. Translation and benchmark work remain paused.
