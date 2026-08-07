# Architecture

## Boundaries

The foundation is a small Python library plus a CLI. JSON Schema remains the
authoritative structural contract. Python modules add cross-record and
conversation rules that JSON Schema cannot express clearly.

## Modules

- `config.py` and `logging.py`: environment configuration and structured logs.
- `schemas`: schema discovery and Draft 2020-12 validation.
- `registry`: canonical tool loading, lookup, schema checking, and duplicate
  detection.
- `ids` and `versioning`: stable identifier and semantic-version rules.
- `validation`: parse, schema, registry, tool-call, message-flow, execution,
  benchmark, and review checks with stable diagnostic codes.
- `execution`: adapter protocol, normalized results, mock/local/stateful examples,
  fixture loading, reset, and explicit mode transitions.
- `blueprints`: blueprint validation and a deliberately narrow candidate
  conversion hook.
- `provenance` and `deduplication`: provenance comparison, deterministic hashes,
  schema fingerprints, duplicate reports, and semantic-similarity protocol.
- `generation`: provider role protocols, mock provider, final-response request
  models, grounding/conflict hooks, and a configuration-gated DeepSeek
  structured-JSON transport.
- `sources` and `localization`: actual xLAM/When2Call source-shape adapters,
  source/license hashes, and natural-language-only Turkish localization patches.
- `network` and `semantic`: injectable JSON HTTP transport, OpenAI embedding
  batches, cosine similarity, and model/text-keyed vector cache.
- `batch`: checksum-bound inputs, target distributions, ID reservations, shards,
  atomic record parts, checkpoint/resume, and failure queues.
- `dataset_workflow`: normal-mode blueprint preflight, active-source enforcement,
  automatic job paths/ID continuation, frozen input distributions, and removal
  of untrusted provider quality/review claims.
- `quality`: automatic dataset evidence recomputation, declared-mode tool
  execution, recorded-result comparison, deterministic/semantic duplicate
  decisions, and per-record quality reports without human acceptance.
- `access`: active principals, lifecycle scopes, permissions, reviewer roles,
  dataset/benchmark team separation, and hash-chained audit events.
- `evaluation`: exact success, five diagnostic criteria, category metrics,
  semantic-judge hook, and isolated run-log writer.
- `review`: review transitions, reviewer-role checks, self-approval prevention,
  revision selection, and accepted-only export.
- `contamination`: cross-corpus benchmark/dataset comparison with blocking and
  semantic-review outcomes.
- `freeze`: validated benchmark-gold snapshots and checksum manifests.
- `reporting`: dataset distribution and benchmark-run summaries.
- `cli`: separate `dataset` and `benchmark` namespaces, source/batch/generation
  operations, access-policy gates, plus shared registry, blueprint, and tool
  commands.

## Data flow

```text
translated/original_turkish/turkey_native
                  |                         |
                  v                         v
data/dataset/{raw,staging,...,accepted}   data/benchmark/{raw,staging,...,accepted}
                  |                         |
                  +---- contamination ------+
                                            |
                                            v
                                data/benchmark/gold + manifest
                                            |
                                            v
                                  runs/<model>/<run>.jsonl
```

Dataset and benchmark lifecycles share schemas, registry versions, categories,
and deterministic components, but never share record content. Benchmark gold is
authored and reviewed independently, checked against the accepted dataset, then
frozen by checksum. Evaluation writes only to `runs/`.

The current operational focus is `original_turkish` and `turkey_native` dataset
generation. Translation/localization and benchmark operations remain available
but paused. Normal `dataset generate` creates the manifest/checkpoint/error paths
under `runs/dataset/<job_id>`; `dataset batch` remains the advanced planning and
resume interface.

Upstream xLAM/When2Call rows first become source localization work items. These
operational records cannot be exported as canonical dataset records. Bulk jobs
bind an immutable input checksum to one lifecycle, one output, one ID range, and
contiguous shards. Per-record part files make resume idempotent; a completed job
cannot be rerun in place.

## Validation flow

1. Parse JSON or one JSONL record at a time.
2. Validate against the selected schema file.
3. Apply registry lookups and input/output schema checks.
4. Validate call/result IDs, names, argument shapes, and message ordering.
5. Apply category, execution, expected-decision, final-response, and review
   consistency rules.
6. Emit stable diagnostics containing code, severity, JSON path, message, and
   optional record/line location.

Schema diagnostics and semantic diagnostics are intentionally separate. An LLM
is never required for deterministic validation.

Generated dataset records cross a trust boundary before validation. The system
checks blueprint metadata, exposed tools, and expected calls, records the actual
provider identity in provenance, forces human review back to `needs_revision`,
and marks any gate without evidence as `not_run`. Provider-supplied `accepted`
or `passed` claims cannot make a draft exportable.

The dataset quality command recomputes deterministic gates, executes local/mock
calls in their declared mode, and compares actual data with recorded tool-result
messages. Real API execution additionally requires explicit live confirmation
and platform permission. Exact/normalized duplicate checks are always run.
Production semantic status can be passed only by the configured OpenAI embedding
path; the token test double can produce diagnostics but not production evidence.
A separate report records execution evidence, pair decisions, model identity,
threshold, actor, and time.

## Execution flow

An adapter declares exactly one execution type. Calls return a normalized result
with status, data, error, timing, and transition history. A requested real API
adapter cannot be substituted by the mock registry. An explicit caller-driven
transition may be made only when both the metadata and log history are updated.
The production HTTP adapter is intentionally narrower than the protocol: HTTPS,
GET, allowlisted hosts, complete argument-to-query mapping, environment-only
credentials, and no side effects.

## Review flow

Automated success makes a record reviewable, not accepted. Review events record
reviewer, role (`language` or `technical`), reviewer decision, previous/computed
overall status, notes, and time. A language approval completes the language gate,
but the overall status remains `needs_revision` while any automatic gate or
required reviewer role is incomplete. Final acceptance rejects contributor
self-approval and enforces two distinct reviewers for marked records. Export
revalidates and emits accepted records only.
CLI mutations additionally require an active scoped principal and permission.
Dataset and benchmark teams can be exclusive, and authorization decisions are
written to a verifiable audit hash chain. Filesystem/object-store ACLs remain a
separate deployment responsibility.
