# Current limitations

- The repository contains production-shaped infrastructure, not a completed or
  published 1,000-record dataset. Proposal tools and blueprints remain subject
  to per-PR validation and review.
- A `candidate` proposal does not by itself prove that a live API,
  license, quota, or long-term access has been approved.
- Standalone `dataset validate` and `benchmark validate` use the canonical
  registry and do not accept a registry override. Proposal-backed drafts are
  validated inside `dataset generate` and `dataset quality --registry ...`;
  accepted records must resolve against the canonical registry used by CI.
- The canonical registry has three `demo` tools for infrastructure tests. It is
  not a production tool catalog. A fixture may be simulated data or an
  approved frozen snapshot; its provenance must say which.
- `sandbox` exists in the execution contract but has no runnable adapter.
- The generic live adapter supports only approved, read-only HTTPS GET JSON
  contracts. It does not support POST, payments, email, or other side effects.
- OpenAI judging and semantic similarity are automated quality evidence, not
  human approval. Turkish naturalness, tool necessity, provenance, and source
  rights still require PR review.
- Reviewer identity and approval history live in GitHub. Repository rulesets and
  storage access controls must be configured outside the CLI. Export trusts the
  committed lifecycle fields and does not query GitHub approval state.
- Translation/import and benchmark production are outside the current active
  workflow. Their namespaces remain available but must not be mixed with active
  dataset production.
- The code and dataset publication licenses have not been selected. Do not make
  a public release until ownership and compatible source licenses are confirmed.
- Generated working outputs are not canonical accepted data. Only deliberately
  selected review packages and the merged canonical accepted dataset belong in
  the documented Git paths.
