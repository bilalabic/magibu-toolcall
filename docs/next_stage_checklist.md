# Next safe step: 20–30-example technical pilot

Do not generate candidates yet. First complete this exact gate:

1. Research several safe, read-only general and Türkiye-native tools using the
   proposal template; confirm API access, licenses, freshness, and fixture plans.
2. Team-approve a small diverse subset and change their lifecycle from
   `candidate` to `approved`; bump only the `0.x` registry version as required.
3. Select DeepSeek/OpenAI model identifiers, semantic rubrics/thresholds, retry
   limits, and budget. Store credentials only in environment variables.
4. Assign contributor ID ranges and language/technical reviewers. Assign a
   benchmark team independent from the dataset team, create a policy validated
   by `schemas/access_policy.schema.json`, and apply storage ACLs.
5. Author separate dataset and benchmark blueprints covering all five
   categories, both parallel and sequential structures, all three source types
   where evidence permits, and multiple difficulties/domains. Never copy records
   or simple paraphrases between lifecycles.
6. Create separate checksum-bound dataset/benchmark batch manifests. Make each
   target distribution equal the blueprint metadata distribution, reserve ID
   ranges, and run collision preflight against accepted records.
7. Validate blueprints and generate dataset and benchmark candidates in separate small batches,
   execute/fix fixtures, regenerate grounded Turkish responses, run deterministic
   and semantic checks, and review every record. Run cross-corpus contamination
   checks before freezing any benchmark gold.
8. Analyze failures and revise schemas/validators while versions remain `0.x`.
   Only after this gate passes may 250-example production begin.
