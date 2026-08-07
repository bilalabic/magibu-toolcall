# Versioning and IDs

Development begins at `schema_version=0.1.0` and
`tool_registry_version=0.1.0`. Do not publish `1.0.0` until the 20–30-example
pilot, validator stabilization, team review, and incompatible-issue resolution.

Change `schema_version` for required-field, field-type, messages, or tool-call
contract changes. Change `tool_registry_version` when tools are added/removed or
their input/output/required parameters/execution environment changes. A
backward-incompatible tool schema change increments the tool ID major, such as
`weather.get_forecast.v1` to `.v2`; descriptions and spelling corrections do not.

Central ID formats are:

```text
tctr_tr_000001  tctr_ot_000001  tctr_tn_000001
bench_tr_000001 bench_ot_000001 bench_tn_000001
call_001
```

Use `dataset generate-id` or `benchmark generate-id`. Source prefixes are validated, collisions and optional
contributor ranges are enforced, and accepted record IDs are immutable.
