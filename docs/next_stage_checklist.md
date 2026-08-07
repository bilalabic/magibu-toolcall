# Next safe step: 20–30-example technical pilot

Do not generate candidates yet. First complete this exact gate:

1. Research several safe, read-only general and Türkiye-native tools using the
   proposal template; confirm API access, licenses, freshness, and fixture plans.
2. Team-approve a small diverse subset and change their lifecycle from
   `candidate` to `approved`; bump only the `0.x` registry version as required.
3. Select DeepSeek/OpenAI model identifiers, semantic rubrics/thresholds, retry
   limits, and budget. Store credentials only in environment variables.
4. Assign contributor ID ranges, a dataset quality operator, and language/
   technical reviewers. Create a policy validated by
   `schemas/access_policy.schema.json`, grant only required permissions, and
   apply storage ACLs.
5. Author dataset blueprints covering all five categories, both parallel and
   sequential structures, `original_turkish` and `turkey_native` source types,
   and multiple difficulties/domains.
6. Run normal `dataset generate`; let it freeze checksum, distribution, ID,
   checkpoint, and error paths automatically. Use advanced batch commands only
   for explicit planning or resume.
7. Run `dataset quality` against the accepted reference corpus. Require declared
   execution evidence, production semantic evidence where comparisons exist,
   no duplicate failures, a durable quality report, then language and required
   technical reviewer approvals before export.
8. Analyze failures and revise schemas/validators while versions remain `0.x`.
   Only after this gate passes may 250-example production begin.

Translation/localization and benchmark work remain paused during this pilot.
