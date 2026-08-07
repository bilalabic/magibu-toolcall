# Requirement traceability matrix

Status values: **implemented**, **implemented-interface**,
**deferred-production**, and **decision-pending**. The validation/test columns
name the implemented rule or test family.

| Requirement | Planned modules/files | Validation/tests | Status / deferral |
|---|---|---|---|
| Repository layout, config, logs, CLI | `pyproject.toml`, `.env.example`, `src/tool_call_tr`, data/registry/runs dirs | imports, CLI help, config/log tests | implemented |
| Dataset shared format | `schemas/dataset.schema.json` | valid/invalid schema + semantic flow tests | implemented |
| Benchmark format and gold isolation | `schemas/benchmark.schema.json`, `evaluation/`, `data/benchmark`, `runs/` | expected consistency and run writer tests | implemented |
| Parallel dataset/benchmark lifecycle isolation | `cli.py`, `data/dataset/`, `data/benchmark/`, `review/` | namespace, path, review, and export tests | implemented |
| Canonical registry and tool metadata | `schemas/tool_registry.schema.json`, `registry.py`, `registry/registry.jsonl` | meta-schema, lookup, duplicate, lifecycle tests | implemented; final tools decision-pending |
| Scenario blueprints and category fixtures | `schemas/scenario_blueprint.schema.json`, `blueprints.py`, fixtures | five valid categories, invalid/priority tests | implemented; production blueprints deferred-production |
| Deterministic diagnostics and exit codes | `validation/*`, `cli.py` | code/path/severity/JSON output/exit-code tests | implemented |
| Tool/function/parameter/ID/version rules | schemas, `registry.py`, `ids.py`, `versioning.py` | format, required, enum, additional, collision tests | implemented |
| Conversation/tool result consistency | `validation/rules.py` | unique/matching IDs, name, parallel/sequential tests | implemented |
| Execution environments and normalized statuses | `execution/*` | mock/local/simulation/HTTPS JSON, all normalized status tests | implemented; final Türkiye-native tools decision-pending |
| No silent real-to-mock fallback | `execution/core.py` | mismatch raises; explicit transition logs test | implemented |
| Final response methods/grounding | dataset schema, `generation/final_response.py` | applicability/default/conflict/failure tests | implemented-interface; production regeneration deferred-production |
| DeepSeek/OpenAI role boundaries | `generation/providers.py`, `network.py`, `semantic.py`, config | structured JSON, retry classification, secret-safe errors, embeddings/cache and strict judge tests | implemented-production-transport; live credentials/pilot pending |
| Provenance and license chain | schema definitions, `provenance.py` | source-type requirements/comparison tests | implemented; source licenses decision-pending |
| Exact/normalized duplicate checks | `deduplication.py` | hashes, placeholder-aware normalization tests | implemented |
| Semantic/combined duplicate support | `deduplication.py`, `semantic.py` | deterministic double plus OpenAI embedding/cosine/cache tests | implemented; production model/threshold approval decision-pending |
| Dataset-to-benchmark contamination gate | `contamination.py`, `benchmark contamination-check` | exact/combined/token-test/OpenAI provider selection tests | implemented; production threshold decision-pending |
| Benchmark exact + five-point scoring | `evaluation/evaluator.py` | seven deterministic distinction cases | implemented; final model results deferred-production |
| Benchmark freeze and immutability audit | `freeze.py`, `benchmark freeze`, `benchmark verify-freeze` | accepted-only validation, checksum, tamper-detection tests | implemented |
| Isolated benchmark run/report CLI | `evaluation/runner.py`, `reporting.py` | run-log separation and aggregate-report tests | implemented; live model execution deferred-production |
| Category metrics | `evaluation/evaluator.py` | per-category/tag aggregation tests | implemented |
| Semantic dataset quality evaluation | `OpenAIQualityJudge`, `quality.py`, dataset quality CLI | strict rubric parsing, contradictory pass rejection, primary/escalation disagreement, budget and evidence tests | implemented-production-transport; live calibration pending |
| Human review and accepted export | `review.py`, `access.py`, CLI | roles, two reviewers, self-approval, active/scope/permission/audit tests | implemented; staff identities decision-pending |
| Data volume/distribution targets | `batch.py`, `reporting.py`, job manifest | target/input equality, shards, checkpoint, final delta report tests | implemented-infrastructure; pilot/250/1,000 runs deferred-production |
| Tool/API research and approved list | proposal template and registry lifecycle | future approval audit | decision-pending; no final list now |
| Dataset Card, final QA/error report | handover checklist | future publication review | deferred-production |
| Benchmark contamination/semantic Turkish QA at scale | protocols and hash hooks | future semantic/human QA | deferred-production |
| Stable `1.0.0` publication | version policy | future pilot/team approval gate | deferred-production |
| Real xLAM/When2Call source import | source-work-item schema, `sources.py`, dataset CLI | official field-shape fixtures, stringified JSON, provenance, malformed-row tests | implemented; source download/terms remain operator-controlled |
| Turkish localization workflow | `localization.py`, dataset CLI | natural-language patching and machine-field preservation tests | implemented; human language approval remains mandatory |
| Resumable bulk Turkish scenario generation | `batch.py`, generation providers, dataset/benchmark CLI | shard, bounded concurrency, checkpoint, retry, failure queue, collision, budget, and resume tests | implemented-infrastructure; production run/spend deferred |
| Türkiye-native real API execution | registry HTTP contract, `execution/http_api.py`, tool CLI | HTTPS GET allowlist, injected transport, timeout/rate-limit/invalid JSON tests | implemented-adapter; final API/tool approval decision-pending |
| Production semantic similarity | `semantic.py`, OpenAI embedding transport, dedupe/contamination CLI | cosine, unique-text batching, cache, compact findings, malformed response, config-gate tests | implemented; threshold approval decision-pending |
| Reviewer directory and access policy | access-policy schema, `access.py`, review/export/freeze/run gates | active principal, role, permission, lifecycle scope, self-approval, benchmark isolation tests | implemented; actual staff identities decision-pending |
| Large-scale distribution plans | job-manifest schema, `batch.py`, `reporting.py` | target/input equality, shard coverage, input hash, checkpoint and distribution-delta tests | implemented-infrastructure; 250/1,000 and 100/150-200 production runs deferred |
| Quality-first normal dataset generation | `dataset_workflow.py`, `dataset generate`, `dataset batch run` | full blueprint preflight, active source restriction, automatic distribution/ID plan, provider self-certification rejection, resume tests | implemented; live provider generation pending |
| Evidence-backed dataset quality | `quality.py`, `dataset quality`, review decision workflow | local execution/result comparison, exact/embedding duplicate states, OpenAI primary/escalation judge, budgets, test-double non-certification, reports, computed reviewer acceptance | implemented; live calibration and real reviewer decisions pending |
| Secret-safe local provider configuration | ignored `.env`, `config.py`, `magibu-toolcall config` | file/process precedence and redacted-output tests | implemented; operator supplies credentials locally |

## Completion categories at handover

- Fully implemented infrastructure: deterministic schemas/validation, source
  import/localization, DeepSeek structured transport, OpenAI embedding
  similarity/cache, read-only HTTPS API execution, access/audit policy,
  resumable batch jobs, evaluator, review/export, CLI, and end-to-end fixtures.
- Partially implemented by deliberate boundary: benchmark free-text response
  judging, production final-answer regeneration, and state-changing sandboxes.
- Operationally supported but not executed: production generation,
  localization, semantic scans, human review, and benchmark runs at target scale.
- Blocked on external decisions/evidence: approved tool list, licenses/API
  access, live provider calibration, duplicate threshold approval, reviewer
  identities, storage ACLs, and measured pilot budgets.
