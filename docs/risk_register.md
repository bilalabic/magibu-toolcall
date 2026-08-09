# Risk register

| Risk | Impact | Current mitigation | Later owner/action |
|---|---|---|---|
| Schema too strict before pilot evidence | Blocks valid cases | `0.1.0`, composable definitions, semantic rules outside schema | Pilot team proposes versioned changes |
| Schema too permissive | Bad records pass syntax | layered semantic validator and mandatory review | Analyze pilot diagnostics |
| Mutable API results in benchmark | Non-reproducible gold | fixed fixture references; no live gold | Benchmark team freezes provenance-backed fixtures |
| Silent execution fallback | False evidence | adapter mode assertion and explicit transition history | Integration owners preserve rule |
| Benchmark leakage | Invalid evaluation | separate paths and hash/fingerprint hooks | GitHub rulesets, storage ACLs, and semantic scan |
| Near duplicates with entity swaps | Inflated diversity | entity-placeholder normalized hash plus semantic interface | Select model/threshold later |
| LLM judges replace deterministic checks | Unreliable QA | hard module boundary and rule-based CLI | Review provider integrations |
| Turkish quality cannot be deterministic | Unnatural records | semantic hook plus GitHub PR checklist | Native reviewer approval |
| Self-approval or insufficient review | Quality/governance failure | required GitHub PR approval, stale-approval dismissal, optional CODEOWNERS | Repository owners maintain rulesets and sampling plan |
| Tool/license metadata becomes stale | Legal/technical risk | explicit status, checked date, freshness risk | Scheduled research review |
| Contributor ID collisions | Unstable accepted IDs | central collision checks and ranges | Assign ranges before pilot |
| Fixture mistaken for production data | Scope/reporting error | `demo` lifecycle and fixture-only paths | Keep fixtures excluded from exports |
| Gated source imported without accepted terms | License/compliance failure | xLAM import requires an explicit operator acknowledgement and preserves license/source hashes | Dataset owner retains acceptance evidence |
| Source localization changes machine fields | Broken calls or provenance | localization patch allowlist plus machine-field fingerprint comparison | Technical reviewer resolves blocked patches |
| Bulk job rerun duplicates or overwrites output | ID/data corruption | input checksum, shard ranges, checkpoint, collision preflight, no overwrite by default | Operator investigates failure queue before resume |
| Secret or unsafe endpoint in real API execution | Credential/data exposure | HTTPS GET only, host allowlist, environment-only credentials, redacted errors | Tool owner reviews registry HTTP contract |
| Embedding provider drift or repeated cost | unstable duplicate decisions/cost | explicit model identity, vector cache, threshold recorded in reports | Data lead approves model and threshold |
| GitHub review mistaken for storage security | benchmark leakage | repository rulesets protect Git history and merges | Infrastructure owner applies OS/object-store ACLs separately |
