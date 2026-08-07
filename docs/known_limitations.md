# Known limitations

- DeepSeek structured generation, OpenAI embeddings/structured dataset judging,
  and read-only HTTPS JSON execution are implemented but no live request is made
  by the test suite or this handover. Credentials remain local; observed costs,
  quota behavior, rubric calibration, and final thresholds still require the
  gated pilot.
- OpenAI embedding similarity is production-capable; semantic judging of free
  text benchmark responses remains a separate provider interface/test double.
- Turkish naturalness, tool necessity, clarification adequacy, and broad factual
  grounding have a primary/escalation model-judge gate but still require human
  review; the judge has not yet been calibrated against human labels.
- The dataset quality command can certify declared local/mock execution and
  compare recorded results. Sandbox execution remains pending; real API quality
  execution requires explicit confirmation, approved registry tools, and live
  platform authorization.
- Human language approval is intentionally not automated. Deterministic model
  and similarity test doubles cannot certify production quality gates.
- Entity-shape duplicate detection needs supplied entity values; production NER
  is deferred.
- The local/stateful adapters are demonstration contracts, not approved tools.
- Application-level access policy, isolated team scopes, permissions, and audit
  hashes are included. They do not enforce OS, Git host, or object-store ACLs.
- xLAM/When2Call local-file import and localization are implemented. Gated source
  download, terms acceptance evidence, and human Turkish/source review remain
  operator responsibilities.
- The real API adapter is intentionally limited to read-only HTTPS JSON. No final
  Türkiye-native API is approved or committed in the registry.
- Benchmark freeze detects later modification through a checksum manifest; it
  does not provide operating-system or remote object-store write protection.
- Sharded/checkpointed bounded-concurrency throughput, compact batched duplicate
  scanning, token budgets, and target-distribution reporting are included;
  the actual 250/1,000 dataset runs, 100/150-200 benchmark runs, final Dataset
  Card, quality/error analysis, and benchmark results remain absent.
