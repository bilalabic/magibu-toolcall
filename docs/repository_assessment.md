# Repository assessment

Assessment date: 2026-08-06

## Existing state

The workspace was empty at inspection time. It contained no source files, Git
metadata, dependency declarations, schemas, scripts, tests, documentation, or
repository-local instructions. There are therefore no existing interfaces or
backward-compatibility commitments to preserve.

## Decisions and assumptions

- Use Python 3.11 or newer with a `src/` layout.
- Use JSON Schema Draft 2020-12 and `jsonschema`; use `pytest` for tests.
- Keep runtime dependencies to `jsonschema`; avoid Pydantic until runtime model
  coercion or richer serialization demonstrably warrants it.
- Store production-shaped dataset and benchmark records only as JSONL. Individual
  JSON fixture files are test inputs, not another processed-data format.
- Treat the five main categories as mutually exclusive and enforce the priority
  rules semantically after schema validation.
- Treat `parallel_tool` and `sequential_tool` as mutually exclusive on a record.
- Use demonstration tools and fixed fixtures only. Their lifecycle is `demo`, not
  `approved`, and they are not a proposed pilot tool list.
- Keep schema and registry versions at `0.1.0` throughout this task.
- Represent execution statuses in normalized result objects and record explicit
  mode transitions; never infer or silently apply a fallback.
- Store training records under `data/dataset/`, benchmark candidates/frozen gold
  under `data/benchmark/`, and model outputs under
  `runs/<model_name>/<run_id>.jsonl`; never copy records between lifecycles.

## Specification clarifications resolved conservatively

- The prompt describes both a tool registry record and a registry JSONL file.
  Each JSONL line will be one canonical registry record validated by the registry
  schema.
- The prompt asks schemas to validate JSON Schema input/output schemas. The
  registry schema checks their declared shape; the registry loader additionally
  calls `Draft202012Validator.check_schema` for meta-schema correctness.
- Semantic response quality and Turkish naturalness cannot be proved
  deterministically. The foundation exposes judge/provider hooks and records
  `not_run` until a semantic judge and human reviewer act.
- "Sequential" is represented by separate assistant tool-call messages with an
  intervening tool result; "parallel" is represented by multiple calls in one
  assistant message. This gives the deterministic validator an unambiguous rule.
- A final assistant message after a successful tool result requires
  `metadata.final_response_method`. No-tool and pre-call clarification records
  must omit it.

## Conflicts

No repository conflicts exist. The attachment contains mojibake in rendered
Turkish examples; new fixtures will use correct UTF-8 Turkish rather than copy
the corrupted rendering.

## Production-readiness reassessment (2026-08-06)

The infrastructure baseline was reassessed before adding production workflow
support. The 94-test baseline passed and the dataset/benchmark lifecycle split
is structurally sound. The following gaps are real implementation gaps rather
than documentation gaps:

- xLAM and When2Call have no source-format adapters or localization work-item
  contract.
- Record I/O loads complete corpora into memory and has no shard/checkpoint job
  manifest.
- DeepSeek/OpenAI classes only check configuration; they do not implement a
  transport, structured response parsing, embeddings, caching, or retryable
  HTTP failures.
- `real_api` is represented by the execution protocol but has no HTTPS,
  read-only, allowlisted JSON adapter.
- Reviewer identity and merge approval belong to GitHub PRs; the CLI should not
  grow an application-level user, role, or permission directory.
- Corpus reporting describes actual distributions but cannot compare them with
  a planned source/category/domain/difficulty distribution.

The existing schemas, validator, registry, execution engine, provenance,
deduplication, GitHub PR review convention, contamination gate, freeze manifest, and
isolated run writer will be extended rather than replaced. Imported source work
items and batch manifests are operational artifacts only; accepted dataset and
benchmark records retain their single canonical schemas.
