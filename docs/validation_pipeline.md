# Validation pipeline and commands

The full validator runs in this order: parse JSON/JSONL, apply the selected JSON
Schema, resolve functions against the registry, validate arguments/results,
check message flow/category priority, check execution/final-response metadata,
check benchmark `expected`, and check review consistency.

Representative codes include `JSONL_RECORD_PARSE_ERROR`, `SCHEMA_REQUIRED`,
`FUNCTION_NOT_IN_REGISTRY`, `ARG_REQUIRED`, `ARG_TYPE`, `ARG_ENUM`,
`ARG_UNSUPPORTED`, `DUPLICATE_TOOL_CALL_ID`, `UNMATCHED_TOOL_RESULT`,
`TOOL_RESULT_NAME_MISMATCH`, `PARALLEL_STRUCTURE_INVALID`,
`SEQUENTIAL_ORDER_INVALID`, `FINAL_RESPONSE_METHOD_REQUIRED`,
`BENCHMARK_DECISION_INCONSISTENT`, and `REVIEW_ACCEPTED_BEFORE_VALIDATION`.

```text
magibu-toolcall dataset validate <file.json-or-jsonl>
magibu-toolcall benchmark validate <file.json-or-jsonl> --output json
magibu-toolcall registry validate registry/registry.jsonl
magibu-toolcall blueprint validate <file.json>
```

Syntactic success is not semantic success. Natural Turkish, tool necessity,
clarification quality, and response grounding require the semantic-judge and
human-review stages. The infrastructure never marks those stages passed merely
because the schema passes.
