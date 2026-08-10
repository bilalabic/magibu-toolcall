# Validation

Validation is layered so deterministic structure, model-assisted quality, and
human judgment remain separate. JSON Schema is the structural source of truth;
Python rules cover cross-record and conversation constraints that schemas cannot
express clearly.

## Deterministic pipeline

The validator runs in this order:

1. Parse JSON or JSONL and preserve line locations.
2. Apply the selected Draft 2020-12 JSON Schema.
3. Resolve functions against the active registry and validate input/output
   schemas.
4. Check call/result IDs, function names, argument shapes, and message ordering.
5. Check category priority, execution metadata, expected decisions, final
   response metadata, and review consistency.
6. Emit stable diagnostics with code, severity, JSON path, message, and optional
   record/line location.

Representative diagnostic codes include:

- `JSONL_RECORD_PARSE_ERROR`, `SCHEMA_REQUIRED`
- `FUNCTION_NOT_IN_REGISTRY`, `ARG_REQUIRED`, `ARG_TYPE`, `ARG_ENUM`
- `DUPLICATE_TOOL_CALL_ID`, `UNMATCHED_TOOL_RESULT`
- `PARALLEL_STRUCTURE_INVALID`, `SEQUENTIAL_ORDER_INVALID`
- `FINAL_RESPONSE_METHOD_REQUIRED`, `NATURAL_TEXT_INTERNAL_MARKER`
- `BENCHMARK_DECISION_INCONSISTENT`
- `REVIEW_ACCEPTED_BEFORE_VALIDATION`

Any error gives the CLI a non-zero exit status. Text and JSON output formats are
available where documented by `--help`.

## CLI commands

```text
magibu-toolcall dataset validate <file.json-or-jsonl>
magibu-toolcall benchmark validate <file.json-or-jsonl> --output json
magibu-toolcall registry validate registry/registry.jsonl
magibu-toolcall registry validate registry/proposals/registry.jsonl
magibu-toolcall blueprint validate <file.json-or-jsonl> --registry registry/proposals/registry.jsonl
```

The proposal commands apply after `registry/proposals/registry.jsonl` has been
created; the repository currently has no active proposal registry. `dataset
validate` and `benchmark validate` use the canonical registry and do
not currently expose a `--registry` option. Proposal-registry blueprints use the
explicit `blueprint validate --registry ...` path. Generated dataset drafts are
validated against their manifest-bound proposal registry during `dataset
generate` and again by `dataset quality --registry ...`. Committed accepted
records must resolve against the canonical registry used by CI.

## Model and human gates

Syntactic success is not semantic success. Natural Turkish, tool necessity,
clarification quality, final-response grounding, and source suitability need the
configured quality provider and human review. The system never marks those
stages passed merely because a JSON Schema succeeds.

Model evidence is also not human approval. Reviewer identity, discussion, and
approval history remain in GitHub; lifecycle fields in a record are validated
but do not authenticate the reviewer.

## Test strategy

Unit tests isolate parser, schema, registry, execution, conversation, quality,
and export behavior. Integration tests exercise deterministic adapters and the
dataset lifecycle. The complete suite runs locally and in CI with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```
