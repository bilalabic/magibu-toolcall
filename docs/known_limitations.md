# Current limitations

- The repository contains production-shaped infrastructure and pilot assets, not
  a completed or published 1,000-record dataset.
- All 20 proposal tools are still `candidate`. A proposal is not evidence that a
  live API, license, quota, or long-term access has been approved.
- The pilot execution mix is 4 local tools, 14 fixed fixtures, and 2 stateful
  simulations. This is suitable for pipeline verification but not enough source
  diversity for the target dataset.
- `sandbox` exists in the execution contract but has no runnable adapter.
- The generic live adapter supports only approved, read-only HTTPS GET JSON
  contracts. It does not support POST, payments, email, or other side effects.
- OpenAI judging and semantic similarity are automated quality evidence, not
  human approval. Turkish naturalness, tool necessity, provenance, and source
  rights still require PR review.
- Reviewer identity and approval history live in GitHub. Repository rulesets and
  storage access controls must be configured outside the CLI.
- Translation/import and benchmark production are outside the current active
  workflow. Their namespaces remain available but must not be mixed with active
  dataset production.
- The code and dataset publication licenses have not been selected. Do not make
  a public release until ownership and compatible source licenses are confirmed.
- Generated pilot outputs are not canonical accepted data. Only deliberately
  reviewed files are committed under the documented review paths.
