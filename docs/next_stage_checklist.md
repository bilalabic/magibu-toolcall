# Next safe step: 30-example live provider pilot

Do not generate candidates yet. First complete this exact gate:

1. Research several safe, read-only general and Türkiye-native tools using the
   proposal template; confirm API access, licenses, freshness, and fixture plans.
2. Team-approve a small diverse subset and change their lifecycle from
   `candidate` to `approved`; bump only the `0.x` registry version as required.
3. Confirm the pinned pilot choices: `deepseek-v4-pro` generation,
   `gpt-5.4-mini-2026-03-17` primary judging,
   `gpt-5.4-2026-03-05` escalation judging, and
   `text-embedding-3-small` similarity. Load credentials only from process
   environment or the ignored local `.env`; verify `magibu-toolcall config`
   displays only `<configured>` markers.
4. Assign contributor ID ranges, a dataset quality operator, and language/
   technical reviewers. Create a policy validated by
   `schemas/access_policy.schema.json`, grant only required permissions, and
   apply storage ACLs.
5. Author dataset blueprints covering all five categories, both parallel and
   sequential structures, `original_turkish` and `turkey_native` source types,
   and multiple difficulties/domains.
6. Run normal `dataset generate` with a conservative worker limit and explicit
   token budget; let it freeze checksum, distribution, ID, checkpoint, and error
   paths automatically. Use advanced batch commands only for explicit planning
   or resume.
7. Run `dataset quality` with production embeddings, the primary OpenAI judge,
   escalation on every non-pass, and a deterministic 10% pass sample. Require
   execution evidence, no unresolved duplicate/model gate, a durable quality
   report, then language and required technical approvals before export.
8. Reconcile provider usage with the DeepSeek/OpenAI dashboards and confirm that
   the OpenAI shared-traffic incentive is actually applied; do not infer this
   from configuration alone.
9. Analyze failures and revise prompts/rubrics while versions remain `0.x`.
   Proceed through 100-example calibration and 250-example rehearsal before four
   separately budgeted 250-example production runs.

Translation/localization and benchmark work remain paused during this pilot.
