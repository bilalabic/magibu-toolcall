# Deferred decisions and production work

## Team or research approval required

- Final 12–20 pilot tools and their approval status.
- API availability, credentials, quotas, licenses, freshness limits, and stable
  fixtures for each researched Türkiye-native source.
- DeepSeek and OpenAI model identifiers/versions, retry limits, cost budgets, and
  semantic judge rubric thresholds.
- Contributor number ranges, GitHub branch-protection rules, CODEOWNERS scope,
  and the human-review sampling procedure.
- Semantic-similarity model and thresholds for near-duplicate and contamination
  decisions.

## Intentionally deferred by scale

- The 20–30-example technical pilot itself.
- The 250-example dataset and 100-example benchmark.
- The total 1,000-example dataset and 150–200-example benchmark.
- Bulk translation, localization, synthetic generation, conversion, review, and
  deduplication.
- Downloading gated source data, accepting source terms on behalf of a user,
  choosing production model versions/thresholds, and paying for live provider
  runs. Source adapters, production transports, and resumable job mechanics are
  implemented infrastructure; execution remains explicit and configuration-gated.
- Final benchmark model runs/results, Dataset Card, and final quality/error report.
- Final Türkiye-native API/tool selection, credentials, legal approval, and
  stable benchmark fixtures. A read-only real-API adapter is infrastructure, not
  approval of any particular external service.
- Publication of schema, registry, or tool versions as `1.0.0`.

## Exact next production gate

After this foundation passes, the team should research and approve a small,
diverse subset of demonstration-to-pilot tool proposals, freeze registry version
`0.1.x`, assign contributor ID ranges, configure GitHub pull-request protection,
and author 20–30 blueprints covering all categories before generating any
candidates.
