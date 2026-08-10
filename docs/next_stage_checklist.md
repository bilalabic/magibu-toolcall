# Dataset production readiness checklist

Complete these gates before starting and then scaling the next dataset pilot:

1. Approve a small, diverse subset of proposal tools and record the source,
   access, license/terms check date, freshness policy, and fixture plan for each.
2. Replace repetitive synthetic fixtures with versioned, provenance-backed
   snapshots where redistribution is permitted.
3. Add or verify the execution implementation and focused tests for every tool;
   do not mark `sandbox` or `real_api` as supported without a runnable adapter.
4. Review blueprint coverage across all five categories, both active source
   types, domains, difficulties, missing-parameter cases, and parallel/sequential
   multi-tool behavior.
5. Run a small generation job with an explicit token budget, checkpoint, error
   queue, and pinned registry/blueprint checksums.
6. Run deterministic validation, execution, semantic duplicate detection, the
   primary OpenAI judge, and configured escalation sampling.
7. Submit the candidate records and matching quality report through a protected
   GitHub pull request. Resolve automated findings and obtain independent human
   language/technical review.
8. Compare provider usage with provider dashboards and review failure patterns,
   source balance, tool balance, and category coverage.
9. Scale through separate 100- and 250-record readiness gates. Treat these as
   production-decision pilots rather than automatically counting them toward the
   final release. Start four bounded 250-record release jobs only after the
   smaller gates meet the agreed acceptance thresholds.

Translation/import and benchmark production remain separate from this checklist.
