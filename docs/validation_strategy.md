# Validation strategy

Validation uses defense in depth without duplicating JSON Schema rules in Python.

1. The parser reports malformed JSON and JSONL line locations.
2. Draft 2020-12 schemas validate required fields, types, enums, patterns, and
   conditional structural requirements.
3. Cross-reference checks resolve functions against the loaded registry and use
   each canonical input/output schema for arguments/results.
4. Message-flow checks validate call/result identity, function consistency,
   parallel grouping, sequential dependencies, and category priority.
5. Metadata checks enforce no-call execution, final-response applicability,
   benchmark decisions, source-specific provenance, and review consistency.
6. Semantic and Turkish-quality checks remain explicit provider/human stages and
   are never represented as deterministic success unless actually run.

Every issue contains a stable error code, severity, JSON path, human-readable
message, and optional file/line/record location. CLI validation renders either
plain text or JSON and returns a non-zero exit status when any error is present.

Unit tests isolate each layer. Integration tests load actual schemas and registry
fixtures, execute deterministic adapters, validate a candidate, add review events,
and export accepted JSONL. The single full-suite command is documented only after
it has passed.

