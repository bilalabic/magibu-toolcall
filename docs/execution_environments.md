# Execution environments

| Type | Use | Current implementation |
|---|---|---|
| `real_api` | Approved, stable, licensed, read-only external APIs | Generic HTTPS GET JSON adapter with host allowlist, env auth, timeout and status normalization; no approved canonical live tool yet |
| `local_executable` | Deterministic local calculation or versioned lookup | Demo arithmetic; new implementations are registered with focused tests |
| `sandbox` | Isolated state-changing service with reset | Contract only; no runnable adapter |
| `mock` | Exact schema-valid fixed response | Registry fixture adapter |
| `fully_simulated` | Rule-driven state transitions | Resettable key/value infrastructure demo |
| `not_applicable` | No tool call | Normalized `not_called` result |

Normalized statuses are `not_called`, `passed`, `failed`, `timeout`,
`rate_limited`, `empty_result`, and `invalid_result`. Adapters must return their
actual mode. The router rejects mode mismatches and missing adapters; it never
falls back silently. A transition requires an explicit reason and transformation
history entry. Stateful environments must be reset before an independent test
series.

The generic real-API adapter is intentionally read-only. A simple provider can
be declared through `execution.http`; a provider-specific wrapper is required
only when the generic query/header/response-path mapping cannot normalize the
contract. No credentials or personal data belong in fixtures.

Banking, payments, healthcare, e-Government, real accounts, email delivery and
other sensitive or side-effecting tools are outside the active dataset scope.
