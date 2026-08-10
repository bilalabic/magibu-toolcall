# Tool-Calling Dataset Coverage Research

Status: research recommendation; no schema or runtime changes are implemented by this document.

Research date: 2026-08-07

Scope: the dataset pipeline. Translation/import and benchmark production remain deferred and separate.

Reading rule: sections titled **Proposed**, **Recommended**, **Implementation
sequence**, or **Acceptance criteria** describe future design work, not current
`0.1.0` behavior. For implemented commands and present limitations, use the
[technical guide](../README_TEKNIK.md) and
[known limitations](known_limitations.md) as the operational sources of truth.

## Executive decision

There is no single authoritative tool-calling dataset standard. Public datasets share a small core—user request, available tool definitions, and expected calls—but stronger systems add state, execution results, acceptable paths, and explicit evaluation rules.

`magibu-toolcall` should preserve a small release/training record and place richer information in three linked artifacts:

1. **Dataset record**: the conversation, exposed tool schemas, selected calls/results, and compact release-safe metadata.
2. **Scenario blueprint/oracle**: intent, possible paths, dependencies, parameter provenance, state assertions, acceptable alternatives, and policy expectations.
3. **Execution evidence**: per-call request/result trace, runtime identity, state delta, timing, errors, and reproducibility hashes.

The versioned tool registry remains a shared supporting asset. Operational evidence, private evaluator prompts, secrets, and benchmark-only annotations must not be copied into training exports.

This separation provides broad scenario coverage without turning each dataset row into an operational log or making the training format dependent on one provider.

## What the repository already has

The current repository already provides:

- separate dataset, blueprint, registry, provenance, review, and validation schemas;
- explicit decisions for tool call, direct answer, missing information, and inability to answer;
- single-tool, multi-tool, multi-turn, missing-parameter, and no-tool categories;
- parallel/sequential, correction, context, failure, unavailable-tool, empty-result, and invalid-result tags;
- real API, local executable, sandbox, mock, simulation, and no-call contracts;
  the sandbox contract does not yet have a runnable adapter;
- strict tool input/output schemas, registry versions, lifecycle, fixture, and risk fields;
- GitHub PR review history, language/semantic/execution validation, duplicate checks, and benchmark-isolation metadata.

The current infrastructure provides the required core contracts, but the active
proposal and blueprint catalogs are intentionally empty. Some concepts are still
represented at record level when they need to be represented per call, per state
transition, or per source snapshot.

## Main gaps before broad dataset production

| Gap | Why it matters | Recommended owner |
|---|---|---|
| Dataset version and enforced partition role/visibility | Prevents training/evaluation leakage and makes releases reproducible | Dataset record |
| Stable tool contract hash | Detects tool-schema drift independently of registry version labels | Registry + record reference |
| Call dependency graph | Represents sequential, parallel, fan-out/fan-in, conditional, retry, and fallback paths | Blueprint |
| Argument provenance | Distinguishes user-provided values from context, tool output, defaults, and forbidden guesses | Blueprint |
| Acceptable alternative paths | Prevents valid plans from failing exact-path evaluation | Blueprint |
| Initial state, state delta, final-state assertions | Required for stateful tools and outcome-based evaluation | Blueprint + evidence |
| Per-call execution evidence | A record-level `execution.status` cannot explain which call failed or why | Evidence |
| Structured tool results and errors | Preserves HTTP/MCP/local error semantics instead of flattening everything to text | Evidence + release projection |
| Source/spec/fixture snapshot provenance | Makes live and recorded data auditable and redistributable | Registry + evidence |
| Safety and effect vector | A single risk label cannot express consent, permissions, reversibility, PII, cost, and external impact | Registry + blueprint |
| Family, cluster, and leakage identifiers | Split must occur after clustering, not by random row | Audit metadata |
| Runtime identity and determinism | Python, parser, locale, clock, seed, and dependency drift can change results | Evidence |
| Untrusted-output handling | Tool results may contain prompt injection or unsafe instructions | Registry + blueprint |
| Outcome and communication assertions | Correct state alone is insufficient if the final answer omits required facts | Blueprint |

## Proposed data model

### 1. Dataset record: release and training projection

Keep this compact. Recommended required concepts for schema `0.2.x`:

```text
identity:
  record_id
  schema_version
  dataset_version
  language
  locale
  created_at

partition:
  role: train | validation | test
  visibility: internal | public | private
  optional split/fold name

scenario_summary:
  blueprint_id
  domain
  source_type
  decision_target
  taxonomy_labels[]
  difficulty

conversation:
  messages[]
  exposed_tools[{tool_id, contract_hash}]

release_provenance:
  source_record references
  generator reference and GitHub PR/commit reference
  source/spec hashes
  license and redistribution status
  transformation history

audit:
  exact_hash
  normalized_hash
  semantic_cluster_id
  tool_family_id
  leakage_group_id
  canonicalizer_version
  dedup algorithm/model/version/threshold
  benchmark_memberships[]
  exclusion_registry_version
  split_manifest_hash
  quality gate results
```

The canonical record references tools by `tool_id + contract_hash`; it does not duplicate the registry schema. An export profile may inline the immutable schema snapshot required by a target training format. The export profile also decides whether tool result messages and the final assistant response are included. Private evaluator configuration, credentials, raw personal data, and GitHub review discussion are never part of the SFT projection.

### 2. Scenario blueprint and oracle

The blueprint should describe the problem, not a single serialized model answer.

```text
scenario:
  user_goal
  initial_context
  current_time, timezone, locale
  available, hidden, unavailable, and distracting tools
  decision_target
  preconditions and policy constraints

parameters:
  expected values
  provenance per value:
    explicit_user | prior_turn | tool_result | system_context |
    deterministic_default | derived | must_not_infer
  clarification requirements

plan_oracle:
  call nodes with stable IDs
  depends_on edges
  parallel groups
  conditional branches
  retry/fallback rules
  acceptable alternative graphs

outcome_oracle:
  expected result schemas
  initial-state assertions
  required state deltas
  final-state invariants
  required communicated facts
  forbidden claims/actions
  canonicalization and tolerances

budgets:
  maximum semantic calls and steps
```

This is compatible with exact-call evaluation for simple examples and outcome-based evaluation for stateful or multi-path examples.

Latency, bytes, CPU, and cost are runtime/evaluator budgets rather than part of the semantic gold oracle. They belong to the selected execution/evaluation profile.

### 3. Execution evidence

Evidence should be append-only and may be regenerated. Each call needs its own trace entry:

```text
identity:
  sample_id, episode_id, call_id, ordinal, parent_call_ids
  optional trace_id/span_id when OpenTelemetry is used

tool_ref:
  namespace, name, version, contract_hash

execution_profile:
  interface, contract_format, transport, mode, state_scope
  mutation, external_impact, determinism_source, repeatability

request:
  redacted source representation and canonical arguments
  request_hash
  state_before_hash

result:
  status
  content blocks
  structured content
  artifacts
  is_error
  normalized and provider error
  state_delta
  state_after_hash

metrics:
  start time, duration, bytes, resource use, optional provider cost

environment:
  source/spec/fixture/code hash
  runtime and dependency identity
  seed, frozen clock, locale, timezone
  redaction manifest
```

Unredacted arguments may exist transiently only inside an isolated collection enclave. They are not written to release evidence. Evidence stores an irreversible redaction, a hash/reference when needed, and a redaction manifest that describes removed field classes without containing the removed secret or personal value.

Recommended normalized errors are `input_validation`, `auth_required`, `auth_denied`, `not_found`, `conflict`, `rate_limited`, `timeout`, `upstream_unavailable`, `policy_denied`, `resource_limit`, `schema_mismatch`, `replay_miss`, `mock_undefined`, `sandbox_violation`, `execution_error`, `cancelled`, and `unknown`. Raw provider codes should also be retained.

### 4. Tool registry contract

The registry should describe independently versioned capabilities:

```text
identity:
  namespace, name, semantic version, contract hash, owner

interface:
  kind, contract format, protocol version, transport, endpoint template

schema:
  JSON Schema dialect, input schema, output schema

semantics:
  preconditions, postconditions, invariants
  effect, reversibility, idempotency, open-world behavior

execution profiles:
  live, local, sandbox, simulation, replay, mock, denied
  time/resource/output/network/filesystem limits

state:
  scope, reset contract, handle schema, expiry, transaction rules

auth and safety:
  scheme, minimum scopes, target audience, secret handling
  target class, sensitivity, confirmation, cost/impact limits

provenance:
  source URL, access date, license/terms status
  spec/code/fixture/dependency hashes
```

The mandatory registry core should remain small: `tool_id`, authoritative `contract_hash`, input/output schema, effect, auth, source, and license/terms status. Provider version and semantic version are recorded when available, but third-party providers are not assumed to publish semver. Preconditions, invariants, state handling, execution profiles, and advanced safety semantics are capability extensions required only when relevant.

## Execution taxonomy

OpenAPI is a contract format and MCP is a protocol/interface; neither determines where or how a tool runs. Store the concepts separately:

```text
interface:
  http | mcp | python |
  filesystem | sql | dataframe | command

contract_format:
  openapi | mcp_schema | json_schema | native | none

transport:
  https | stdio | ipc | in_process

mode:
  live_remote | local_native | sandboxed |
  simulation | replay | mock | denied

state_scope:
  none | call | episode | persistent

mutation:
  none | additive | update | delete

external_impact:
  none | communication | monetary | physical

determinism_source:
  pure | seeded | fixture | external

repeatability:
  exact | semantic | variant
```

`persistent` state is representable for future research but is disabled in the first production wave; the initial implementation is limited to `none`, `call`, and resettable `episode` state.

Recommended practical profiles:

| Profile | Appropriate use | Required boundary |
|---|---|---|
| `http.live` | Current, public, read-only information | HTTPS + host/path allowlist, post-DNS private/loopback/link-local rejection, redirect-hop revalidation, quota, timeout, no silent fallback |
| `mcp.remote` | Remote catalog or data tools | Auth audience/scope checks; tool-list/schema snapshot |
| `mcp.local` | Locally hosted tools | Same process/filesystem/network sandbox boundary as other untrusted local executors; never assume local means trusted |
| `python.pure` | Math, conversion, normalization, deterministic algorithms | Registered callables only; no dynamic import, network, subprocess, `eval`, or `exec` |
| `workspace.filesystem` | Synthetic file search/read/write tasks | Explicit episode mount root, clean environment, reparse-point/symlink rejection or no-follow handles, manifests, reversible deletion |
| `workspace.sqlite` | Query and transactional state tasks | Per-episode clone/in-memory DB, parameterized SQL, rollback and state hashes |
| `workspace.dataframe` | CSV/JSON/Parquet transformations | Local inputs only, pinned parser/dtypes/order/null policy |
| `sandbox.code` | Untrusted generated code | Disposable non-root sandbox; read-only rootfs, no-new-privileges, no capabilities/devices/host sockets, seccomp/LSM, digest-pinned image, process-tree and resource/output limits |
| `simulation.stateful` | Calendar, cart, ticket, inventory, booking, CRM | Reset/step/snapshot API, seed, virtual clock, atomic transitions |
| `fixture.http_replay` | Reproducible real recorded behavior | Canonical matcher, redaction, record time, TTL, hash; no live fallback |
| `mock.spec` | Contract testing from OpenAPI/JSON Schema examples | Mark as synthetic contract, not provider evidence |
| `mock.handwritten` | Behavioral scenarios without a safe provider | Explicit rules; undefined combinations must fail |
| `none.policy_denied` | Intentionally unavailable unsafe action | Expected refusal/policy outcome |

### Local execution rules

- Pure Python uses only allowlisted functions and canonical JSON-compatible arguments/results.
- Arbitrary Python or shell code is a separate sandbox profile and is not required for the first 1,000 records.
- Every episode gets an explicitly mounted isolated workspace and clean environment; host home directories, devices, sockets, repository-external paths, and other episodes are unavailable.
- Filesystem access rejects symlinks/reparse points or uses no-follow, directory-handle-relative operations so a path check cannot be swapped before open.
- Writable filesystem and SQLite scenarios record before/after manifests or hashes.
- Dataframe tools reject URLs even if the underlying library accepts them.
- Runtime, Python, dependency lock, locale, timezone, encoding, seed, and virtual clock are recorded.
- A resource limit or policy refusal is a valid expected result, not an infrastructure accident.

### Stateful simulation contract

```text
reset(seed, scenario_id) -> observation, state_handle
step(state_handle, action) ->
  observation, state_delta, events, terminated, truncated, info
snapshot(state_handle) -> state_hash
close(state_handle)
```

`terminated` means the scenario reached an outcome; `truncated` means a step, time, or resource budget ended it. External effects are emitted as simulated events only.

The state handle is opaque, episode- and tenant-bound, expiring, and authorized on every call. If it is bearer-like, release evidence stores only a masked or re-keyed representation.

## Complete scenario coverage model

The following dimensions overlap. A record has one primary family and multiple orthogonal labels.

| Dimension | Scenarios that must be representable | Main oracle |
|---|---|---|
| Decision | direct answer, tool call, request information, request confirmation, request authorization, cannot answer, missing/unavailable tool, policy refusal | expected decision and reason |
| Selection | single obvious tool, similar tools, distractors, large-catalog retrieval, unseen tool/family | selected/forbidden tools |
| Conversation | single turn, multi-turn, long context, correction, cancellation, confirmation, changed goal, memory | turn-level behavior and retained facts |
| Call topology | single, repeated same tool, parallel, sequential, fan-out/fan-in, conditional branch, fallback | dependency DAG and alternatives |
| Parameters | explicit, implicit, prior-turn, tool-derived, defaults, missing, conflicting, invalid, nested, arrays/enums | value + provenance + must-not-infer rules |
| Time and locale | Turkish morphology, dates, DST, timezone, currency, units, addresses, relative time | frozen context and normalization rules |
| Success results | scalar/object/list, pagination, partial/truncated, empty, large artifact, multimodal/resource reference | schema, evidence, required communicated facts |
| Failures | validation, auth, 403/404/409, 429, timeout, 5xx, malformed/invalid schema, replay miss | expected error class and recovery |
| Recovery | corrected call, idempotent retry, no unsafe retry, alternate tool, rollback, ask user | allowed transition/path |
| Stateful actions | read/create/update/delete, conflict, transaction, rollback, idempotency, stale state | initial/final state and invariants |
| Safety | consent, permissions, PII/secrets, cost, destructive/external effects, high-stakes refusal | policy outcome and redaction assertions |
| Trust | prompt injection in tool output, malicious metadata, conflicting sources, data exfiltration request | untrusted-content handling |
| Grounding | answer from results, uncertainty, freshness, citation/evidence, no unsupported claim | communication assertions |
| Local data | files, directories, text search, SQLite, dataframe, deterministic Python, sandboxed code | artifact/state hash and result checks |
| Tool evolution | schema drift, deprecated/hidden tool, renamed operation, protocol/version mismatch | contract hash and expected fallback |
| Efficiency | unnecessary calls, call/step/cost/latency limits, parallelization opportunity | budget and minimality rules |
| Attribution | user, agent, tool, environment, policy, or upstream failure | fault attribution label |
| Web research | multi-query search, result opening, evidence synthesis, insufficient/contradictory sources | source set and communication assertions |
| Memory operations | add, search, update, remove, clear, irrelevant-memory resistance | episode-local memory state and invariants |
| Format variation | tool-doc layout, call envelope, tag syntax, prompt framing, response style | semantic equivalence across format variants |

Additional advanced categories supported by the design but not required in the first production wave are asynchronous jobs, streaming/chunked results, multimodal MCP content, cross-server namespace collisions, expiring state handles, concurrency races, and cross-episode persistent memory. Web-research, episode-local memory operations, and format variation should still receive small pilot coverage because they test distinct behavior.

## Domain coverage and safe execution

| Domain | Typical tasks | Primary backend | Restriction |
|---|---|---|---|
| Public/current information | weather, earthquake, transport, geography, open data | read-only live HTTP + replay | external output is untrusted |
| Knowledge/research | documents, catalogs, publications, legislation | live search or official snapshots | preserve source and access date |
| Developer tools | file search, tests, build/static analysis | episode filesystem + sandbox | no host shell or secrets |
| Data analysis | CSV cleanup, joins, aggregations, SQL | dataframe, SQLite, pure Python | episode-local inputs |
| Commerce | product search, cart, order/cancel/return | live read-only search + stateful simulation | no real payment/order |
| Travel | destination/search/itinerary/reservation | read-only API + simulation | no real booking |
| Calendar/tasks | availability, create/move/cancel | stateful simulation | no real invitations |
| Support/CRM | lookup, assign, resolve, summarize | synthetic stateful simulation | no real customer data |
| Logistics/inventory | stock, reservation, shipment status | simulation or licensed read-only source | no physical dispatch |
| Finance | public economic/reference data, synthetic portfolio | read-only official data + simulation | no trade/transfer/advice claim |
| Health | public aggregate statistics, synthetic records | official snapshots + synthetic DB | no real patient data/diagnosis/prescription |
| IoT/industry | sensor reads, alarm plans | simulation | no physical actuation |
| IAM/security | policy analysis, synthetic logs, defensive tasks | simulation/sandbox | no real credential/role change or unauthorized action |

Real email and payment integrations are out of scope. Their reasoning patterns may be represented only through generic simulated state transitions if needed; no provider integration is planned.

## Turkey-native source qualification

Only documented public interfaces are called APIs. Private endpoints discovered behind a public web application are not treated as supported APIs. The source checks in this section were performed on 2026-08-07 and must be repeated before implementation.

### Recommended pilot order

| Priority | Official source | Candidate tools | Preferred mode | Qualification note |
|---|---|---|---|---|
| 1 | [TCMB EVDS](https://evds2.tcmb.gov.tr/index.php?/evds/userDocs=) | economic series search/read, official exchange rates | live read-only + replay | Strong documentation; API key required. [Terms](https://evds2.tcmb.gov.tr/help/videos/EVDS_Disclaimer.pdf) require attribution, prohibit charging specifically for EVDS data in a commercial product, and disclaim investment advice |
| 2 | [AFAD Earthquake Web Service](https://deprem.afad.gov.tr/event-service) | list/filter/get earthquakes | live read-only + replay | Keyless JSON; attribution required; confirm bulk redistribution terms before release |
| 3 | [TR Dizin API](https://development.trdizin.gov.tr/) | publication/journal/author search | live read-only + replay | Documented JSON API. [Published terms](https://trdizin.gov.tr/kullanim-sartlari/) do not establish a clear content license; verify redistribution, minimize author/ORCID data, and remove contact/address fields |
| 4 | [Official holiday law](https://www.mevzuat.gov.tr/mevzuatmetin/1.5.2429.pdf) + [Diyanet religious days](https://vakithesaplama.diyanet.gov.tr/dini_gunler.php) | list holidays, business-day checks | versioned deterministic local tool | Keep legal source/version and distinguish public holiday from administrative leave |
| 5 | [Ministry of Health Open Data](https://acikveri.saglik.gov.tr/) | dataset catalog and individually approved de-identified datasets | versioned local snapshot | [Attribution license](https://acikveri.saglik.gov.tr/app/doc/KullanimKosullari.pdf); review every dataset for re-identification and third-party rights, including medical images |
| 6 | [HGM ATLAS](https://api.harita.gov.tr/) | geocode, reverse geocode, POI search, route | conditional live + replay | API key, quota, beta status; do not retain user coordinates or mirror results; redistribution terms need confirmation |
| 7 | [TUCBS](https://tucbs.gov.tr/) | list/query explicitly open geospatial layers | OGC live/read-only + snapshot | Qualify every layer through the sharing matrix and retain the producer's own terms and attribution; “Open Data” alone is not a redistribution license |

### Second phase

- [EPİAŞ Transparency Platform test documentation](https://seffaflik-prp.epias.com.tr/reporting-service/technical/tr/index.html): valuable energy generation, consumption, and market-price data; freeze the live production host/spec, current CAS/TGT requirements, account contract, and web-service terms before promotion.
- [TÜİK Data Portal](https://veriportali.tuik.gov.tr/): use official table snapshots until a public technical API contract and reuse terms are confirmed.
- [MEB official statistics](https://sgb.meb.gov.tr/istatistik_k/resmi_istatistik.html): annual aggregate Excel/PDF snapshots; never use student/e-School data.
- [ÖSYM](https://www.osym.gov.tr/): dated exam-calendar snapshots only; result and document verification are excluded.
- [Official Gazette](https://www.resmigazete.gov.tr/), [Legislation Information System](https://www.mevzuat.gov.tr/), and [TBMM laws](https://www.tbmm.gov.tr/yasama/kanunlar): link-preserving snapshots with effective/access dates; no unsupported legal advice.
- [Ministry of Culture tourism statistics](https://engelsiz.ktb.gov.tr/TR-201130/metaveri.html) and [Culture Portal](https://www.kulturportali.gov.tr/): metadata or versioned aggregate-table snapshots only; do not mirror portal text or images without explicit rights.
- [İBB Open Data](https://data.ibb.gov.tr/): reconsider dataset by dataset after access stabilizes; the 2026 review encountered 403/availability instability, and each dataset needs its own license decision.

### Snapshot/mock or excluded from real execution

| Source | Policy |
|---|---|
| MGM weather observations/forecasts | No verified public developer API; off-site meteorological data is generally paid/licensed, and free climate projections prohibit third-party sharing/commercial use; use licensed access or a source-dated mock, not hidden endpoints |
| National air-quality UI | Official download/snapshot only until a documented API and redistribution terms exist |
| KGM road status | Dated official bulletin snapshot; do not package the web application's backend as a public API |
| DHMİ flight information | Official page snapshot/fixture only; no reverse-engineered mobile/web endpoint |
| On-duty pharmacy | Snapshot/mock only; no e-Government automation or bulk contact-data reuse |
| PTT shipment tracking | Mock only; tracking identifiers and CAPTCHA make live automation unsuitable |
| TKGM parcel lookup | Exclude from the pilot; sensitive identifiers and contractual data-sharing rules |
| YÖK thesis content | Exclude full text; prefer TR Dizin bibliographic metadata |
| e-Government personal/transactional services | Exclude real calls, credentials, PII, and account actions |

## Source admission gate

Every source/tool progresses independently through:

```text
discovered -> reviewed -> candidate ->
approved_live | approved_replay | approved_local | approved_simulation ->
deprecated
```

Admission requires recorded answers to all of these questions:

1. Is there an official public technical contract, or is this only a web UI?
2. What exact operations, hosts, paths, methods, formats, versions, and quotas are supported?
3. What authentication is required, and can credentials remain outside records and fixtures?
4. Is the operation actually read-only, idempotent, reversible, and free of real-world actuation?
5. Does it process PII, secrets, location, health, financial, or identity data?
6. Do license and terms permit collection, transformation, redistribution, and research release?
7. What attribution and retention rules apply to each dataset or layer?
8. Can responses be validated against a declared output schema?
9. Can a redacted, license-compatible replay fixture be produced?
10. Can rate limits, timeouts, drift, downtime, and deprecation be tested without silent mock fallback?

An unverified source remains a proposal. It must not be promoted because a private JSON endpoint happens to respond.

## Safety levels

| Level | Example | Runtime policy |
|---|---|---|
| G0 | Pure deterministic calculation, read-only synthetic file | Automatic |
| G1 | Allowlisted public read-only API | Automatic with quota and audit |
| G2 | Episode-local reversible mutation | Automatic or scenario-specific confirmation |
| G3 | Limited mutation in a provider test tenant | Disabled in the first wave; later requires explicit confirmation, provider-backed reversibility, rollback, and isolated collection |
| G4 | Money, communication, IAM, credentials, physical action, permanent deletion | Simulation/mock only |
| G5 | Exploitation, malware, exfiltration, bypassing controls | Tool is unavailable; expected policy refusal |

Policy decisions should use a vector rather than one risk score: effect, target class, reversibility, open-world access, data sensitivity, scopes, monetary/physical impact, confirmation, network egress, cost/record/byte limits, retry semantics, and sandbox strength.

## Proposed first-1,000 coverage

Because translation/import is deferred, the first production target can focus on original Turkish and Turkey-native records while leaving the schema ready for derived datasets.

Each record receives one planning-only `dominant_skill`; orthogonal labels such as statefulness, failure, safety, locale, and execution mode are overlaid. To keep the counts deterministic when skills overlap, use this priority: stateful episode, failure/recovery, no-call decision, multi-turn/clarification, sequential/DAG, parallel, selection/retrieval, then single-tool. This dominant label is not the semantic taxonomy and is not exported as the only description of a record.

| Primary family | Count | Purpose |
|---|---:|---|
| Single-tool argument construction | 180 | Core schema and parameter accuracy |
| Tool selection/retrieval with distractors | 150 | Similar tools, unavailable tools, large catalogs |
| Parallel/repeated calls | 120 | Independent calls and aggregation |
| Sequential and dependency-DAG plans | 170 | Output-to-input transfer, fan-out/fan-in, alternatives |
| Multi-turn, clarification, correction, confirmation | 150 | Context and decision quality |
| Direct answer, cannot answer, unavailable tool, policy refusal | 100 | Avoid unnecessary or unsafe calls |
| Execution failure and recovery | 70 | Timeout, rate limit, invalid result, retry/fallback |
| Stateful episode-local scenarios | 60 | Create/update/delete, conflict, rollback, idempotency |
| **Total** | **1,000** | |

Suggested source mix while translation is paused:

- 650 original Turkish general-tool records;
- 350 Turkey-native records;
- translated/derived records remain disabled until that workstream resumes.

Minimum overlay targets across the 1,000 records:

- at least 250 locally executed (pure Python, filesystem, SQLite, or dataframe);
- at least 150 based on qualified live/replay official sources;
- at least 150 state, failure, recovery, or policy-boundary examples;
- at least 100 no-call decisions;
- at least 100 multi-turn records;
- at least 40 web-research, 40 episode-local memory-operation, and 50 paired format-variation cases;
- every tool family represented in success, invalid/missing input, and unavailable/failure conditions where meaningful.

These counts are a planning proposal, not a frozen generation quota. The 100-record schema/execution pilot should determine the final distribution.

## Implementation sequence

### Phase 0 — approve the research decisions

- Approve the three-layer record model and shared registry contract.
- Approve the execution axes and safety levels.
- Approve the first-1,000 source mix and local-execution scope.

### Phase 1 — schema `0.2.x`

- Add dataset version, partition role/visibility, and cluster/leakage identifiers.
- Add stable tool contract hashes and source/license qualification status.
- Add blueprint call DAG, parameter provenance, alternatives, state assertions, communication assertions, and semantic call/step budgets.
- Put latency, bytes, CPU, and cost limits in runtime/evaluator profiles.
- Add a separate execution-evidence schema with per-call results and normalized errors.
- Provide explicit `0.1.0 -> 0.2.x` migration and tests; do not silently reinterpret old records.

### Phase 2 — safe execution coverage

- Expand registered pure-Python tools.
- Add episode-local filesystem, SQLite, and dataframe adapters.
- Add stateful simulator reset/step/snapshot support.
- Add replay fixtures with matching, redaction, hashes, and no-live-fallback behavior.
- Defer arbitrary code execution until a real sandbox boundary exists.

### Phase 3 — source qualification

- Implement source-admission manifests.
- Qualify TCMB EVDS, AFAD, and TR Dizin first.
- Capture compliant fixtures and error cases.
- Evaluate HGM ATLAS and the official snapshot candidates after license/retention checks.

### Phase 4 — 100-record integrated pilot

- Exercise every primary scenario family and every execution profile selected for the first 1,000.
- Run schema, execution, state, semantic, language, dedup, license, and safety gates, then complete human review through a GitHub PR.
- Analyze rejection reasons and revise schemas or generation prompts before scale-up.

### Phase 5 — 1,000-record production

- Generate in bounded batches with frozen tool/spec/runtime versions.
- Cluster before split; keep family members in one split.
- Require execution evidence where execution is expected.
- Require GitHub PR approval and release-compatible provenance/license status.

### Phase 6 — benchmark remains separate

Benchmark creation stays deferred. When resumed, it must use isolated source families, manifests, and preferably an independent authoring pipeline after the training dataset is frozen.

## Acceptance criteria

The architecture is ready for the 100-record integrated pilot when:

- every dataset record references a valid blueprint and versioned tool contract;
- every executable call has per-call evidence and a reproducible execution profile;
- stateful scenarios prove reset determinism and final-state assertions;
- no secret or raw personal data appears in records, logs, or fixtures;
- live sources pass the source-admission gate and have explicit attribution/redistribution status;
- replay misses and adapter mismatches fail closed instead of silently switching mode;
- split/leakage groups are assigned before export;
- direct, clarify, cannot-answer, unavailable-tool, and policy-refusal decisions are validated explicitly;
- acceptable alternative paths are evaluated by outcomes and constraints, not only exact call strings;
- all new schema and executor behavior has unit and end-to-end tests.

## Primary research sources

Dataset and benchmark design:

- [xLAM Function Calling 60k dataset card](https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k)
- [APIGen paper](https://arxiv.org/abs/2406.18518)
- [When2Call repository](https://github.com/NVIDIA/When2Call)
- [When2Call paper](https://aclanthology.org/2025.naacl-long.174/)
- [BFCL repository and test categories](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)
- [BFCL V2 Live collection and deduplication](https://gorilla.cs.berkeley.edu/blogs/12_bfcl_v2_live.html)
- [BFCL multi-turn/state evaluation](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
- [BFCL V4 web search](https://gorilla.cs.berkeley.edu/blogs/15_bfcl_v4_web_search.html)
- [BFCL V4 memory](https://gorilla.cs.berkeley.edu/blogs/16_bfcl_v4_memory.html)
- [BFCL V4 format variation](https://gorilla.cs.berkeley.edu/blogs/17_bfcl_v4_prompt_variation.html)
- [ToolBench repository](https://github.com/OpenBMB/ToolBench)
- [API-Bank paper](https://arxiv.org/abs/2304.08244)
- [Gorilla/APIBench paper](https://arxiv.org/abs/2305.15334)
- [ToolSandbox repository](https://github.com/apple/ToolSandbox)
- [tau-bench repository](https://github.com/sierra-research/tau-bench)
- [AgentDojo repository](https://github.com/ethz-spylab/agentdojo)

Contracts, execution, and safety:

- [OpenAPI Specification 3.2.0](https://spec.openapis.org/oas/v3.2.0.html)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [HTTP semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
- [JSON Canonicalization Scheme, RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)
- [Python subprocess security considerations](https://docs.python.org/3/library/subprocess.html#security-considerations)
- [SQLite transaction semantics](https://sqlite.org/lang_transaction.html)
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [gVisor security model](https://gvisor.dev/docs/architecture_guide/security/)
- [Firecracker design](https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md)
- [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

Turkey-native source links and qualification notes are recorded in the source tables above. Every source must be rechecked at the date of implementation because API versions, access terms, and licenses can change.
