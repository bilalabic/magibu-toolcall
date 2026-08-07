# Execution environments

| Type | Use | Current implementation |
|---|---|---|
| `real_api` | Stable, safe, licensed, read-only external APIs | HTTPS GET JSON adapter with allowlist, env auth, timeout/status normalization |
| `local_executable` | Deterministic local calculation or versioned lookup | `utility_add` and `utility_multiply` demos |
| `sandbox` | Isolated state-changing service with reset | Contract only |
| `mock` | Exact schema-valid fixed responses | Registry fixture adapter |
| `fully_simulated` | Rule-driven state transitions | Resettable key/value example |
| `not_applicable` | No tool call | Normalized `not_called` result |

Normalized statuses are `not_called`, `passed`, `failed`, `timeout`,
`rate_limited`, `empty_result`, and `invalid_result`. Adapters must return their
actual mode. The router rejects mode mismatches and missing adapters; it never
falls back. A transition requires an explicit reason and transformation-history
entry. Sandbox/simulation state must be reset before a test series.

No credentials or personal data belong in fixtures. Banking, payments,
healthcare, e-Government, real accounts, and other sensitive/side-effecting tools
must use sandbox or full simulation during the pilot.
