# Execution environments

| Type | Use | Current implementation |
|---|---|---|
| `real_api` | Approved, stable, licensed, read-only external APIs | Generic HTTPS GET JSON adapter with host allowlist, env auth, timeout and status normalization; no approved canonical live tool yet |
| `local_executable` | Deterministic local calculation or versioned lookup | Module registry under `execution/local/`; each package owns one module |
| `sandbox` | Isolated state-changing service with reset | Contract only; no runnable adapter |
| `mock` | Exact schema-valid fixed response | Registry fixture adapter |
| `fully_simulated` | Rule-driven state transitions | Module registry under `execution/simulation/`; one tool owns one resettable state |
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

## How to contribute in each mode

Every mode follows the same rule the registry and blueprint fragments already
use: **one contribution package owns exactly one file in a shared parent
directory, named `<domain>_<source>`.** No contributor edits a file another
package also edits, so parallel pull requests never collide.

A tool's input and output schemas always live inside its registry record
(`function.parameters` and `output_schema`). The `schemas/` directory holds only
meta-schemas; never add a per-tool schema file.

### `local_executable`

Add `src/tool_call_tr/execution/local/<domain>_<source>.py` publishing a
module-level `FUNCTIONS` mapping. Do not edit `adapters.py`.

```python
"""Offline executor backed by the versioned population snapshot."""

from __future__ import annotations

from typing import Any

from tool_call_tr.execution.local import LocalFunction


def demography_get_population(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return one province/year row from the pinned snapshot."""

    ...


FUNCTIONS: dict[str, LocalFunction] = {
    "demography_get_population": demography_get_population,
}
```

A function receives the already validated `arguments` dictionary and returns the
output payload. Raising is allowed: the adapter boundary maps an exception to
`failed`, and `ExecutionTimeout` / `ExecutionRateLimited` to their own statuses.

A module that answers from a pinned snapshot resolves it with `snapshot_dir`
rather than counting parent directories:

```python
from tool_call_tr.snapshots import snapshot_dir

SNAPSHOT_ROOT = snapshot_dir("tuik", "migration", "v1")
```

`Path(__file__).resolve().parents[N]` breaks silently the moment a module moves
between directories, and it is wrong outside a source checkout because `data/`
is not package data. `snapshot_dir` keeps that arithmetic in one place and reads
`MAGIBU_SNAPSHOT_ROOT` when the snapshot tree lives elsewhere. It does not
require the directory to exist; report a missing snapshot in your own error
vocabulary.

Discovery imports the modules in sorted name order and never swallows an import
error. `LocalModuleError` is raised when a module has no `FUNCTIONS` mapping, or
when two modules claim the same function name — the message names both modules.

Reference module: [`local/utility_demo.py`](../src/tool_call_tr/execution/local/utility_demo.py).

Acceptance criteria: deterministic, no network at call time, conforming to the
declared input and output schemas, and covered by tests for a valid call, an
invalid or missing argument, and the tool's own failure path.

### `fully_simulated`

Add `src/tool_call_tr/execution/simulation/<domain>_<source>.py` publishing a
module-level `TOOLS` sequence. One tool owns one state and may serve several
function names, so sibling operations — availability, reservation, cancellation —
act on the same simulated world.

```python
class StudyRoomTool:
    """Availability and reservation over one shared state."""

    function_names = ("education_check_room_availability", "education_book_study_room")

    def initial_state(self) -> Any:
        return {"reservations": {}}

    def execute(self, state: Any, function_name: str, arguments: dict[str, Any]) -> Any:
        ...


TOOLS = (StudyRoomTool(),)
```

`execute` mutates `state` in place and returns the result payload. `reset()`
rebuilds every tool's state from `initial_state()`; a contribution is accepted
only when a test proves that reset returns the world to exactly that value.
`SimulationModuleError` is raised for a missing `TOOLS` sequence, an object that
does not satisfy the protocol, or a duplicate function name.

Reference module: [`simulation/kv_demo.py`](../src/tool_call_tr/execution/simulation/kv_demo.py).

A confirmation flow has no dedicated `expected_behavior` value; express it as a
`multi_turn` blueprint carrying the `confirmation_required` secondary tag.

### `mock`

Add `registry/proposals/fixtures/<fixture_id>.json` and list the identifier in
the registry record's `execution.fixture_ids`. No code change is needed; the
existing mock adapter serves the fixture.

A fixture is matched on the exact argument set, so one fixture answers one
argument combination. `load_fixture` validates both the arguments and the result
against the tool's schemas, and an unmatched call returns
`mock_fixture_not_found`.

```powershell
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture <fixture_id> --registry registry\proposals
```

### `real_api`

Declare the contract in the registry record's `execution.http`. Only HTTPS GET,
an explicit host allowlist, environment-variable credentials and a timeout are
allowed.

An **optional** query parameter is declared in `function.parameters.properties`
and in `execution.http.query_map`, but is left out of
`function.parameters.required`:

```json
"parameters": {
  "type": "object",
  "properties": {
    "city": {"type": "string", "description": "İl adı."},
    "station_id": {"type": "string", "description": "İstasyon kimliği (isteğe bağlı filtre)."}
  },
  "required": ["city"],
  "additionalProperties": false
},
"query_map": {"city": "city", "station_id": "station"}
```

An omitted optional parameter never reaches the query string. Required arguments
are enforced earlier, by the parameter schema in `ExecutionEngine.execute`, so
the adapter only checks that every supplied argument has a `query_map` entry; an
unmapped argument fails with `http_argument_not_mapped` before any request is
made.

Test without touching the network by injecting a `JsonTransport` implementation
into `HttpJsonAdapter`. `tests/conftest.py` blocks the live transport, so
injection is mandatory rather than optional. Copy
[`tests/unit/test_http_api_optional_query.py`](../tests/unit/test_http_api_optional_query.py)
as the starting point.

One live call can be made from the CLI. A candidate contribution needs two
deliberate confirmations:

```powershell
.\.venv\Scripts\magibu-toolcall.exe tool run-api <function_name> `
  --arguments '{"city": "Ankara"}' `
  --registry registry\proposals --confirm-live --allow-candidate
```

`--registry` accepts a JSONL file or a fragment directory and defaults to the
canonical registry. `--allow-candidate` widens the gate to the `candidate`
lifecycle only; `demo` and `deprecated` stay blocked, and `--confirm-live`
remains required.

### `sandbox`

No runnable adapter exists. A contribution in this mode must bring its own
adapter and isolation tests, so agree on the design before starting.

## Versioned source snapshots

A `local_executable` tool that answers from official published data pins that
data as a versioned snapshot under `data/snapshots/`. Each snapshot owns one
directory holding exactly these three things:

```
data/snapshots/<provider>/<dataset>/<version>/
├── provenance.json
├── raw/<original published files>
└── <data_file>
```

The directory path is descriptive and may be nested as above or flattened to a
single `<snapshot_version>` directory; validation discovers every
`provenance.json` beneath `data/snapshots/`. What is fixed is the content: one
`provenance.json`, the raw files it declares, and the data file it names.

`provenance.json` is validated against
[`schemas/snapshot_provenance.schema.json`](../schemas/snapshot_provenance.schema.json).
Every raw file carries a mandatory `sha256`, which is what makes the snapshot
auditable: the declared bytes and the committed bytes are compared on every pull
request.

```json
{
  "snapshot_provenance_version": "0.1.0",
  "provider": "TÜİK",
  "source_name": "Adrese Dayalı Nüfus Kayıt Sistemi, 2024",
  "snapshot_version": "tuik-population-2024-v1",
  "retrieved_at": "2026-08-15",
  "license": "TÜİK verileri kaynak gösterilerek yeniden kullanılabilir.",
  "license_url": "https://www.tuik.gov.tr/Kurumsal/Yasal_Uyari",
  "data_file": "population_2024.csv",
  "sources": [
    {
      "raw_file": "raw/population_2024.xls",
      "sha256": "9901851288f108380752cc61c906441bdde9f919f42b31353f8cf9e8c44d1eb9",
      "release_id": "49685",
      "source_url": "https://data.tuik.gov.tr/Bulten/Index?p=49685",
      "release_date": "2025-02-06",
      "label": "2024"
    }
  ],
  "transformation_notes": ["Province rows were copied verbatim from the published table."]
}
```

Field notes:

- `snapshot_version` is kebab-case ending in `-v<N>`, and the number rises
  whenever the raw data or the transformation changes.
- `sources` is a list, so a snapshot built from one file and a snapshot built
  from one file per year share the same shape; `label` carries the period. When
  each release has its own official title, put it in the entry's optional
  `source_name`; the top-level `source_name` then names the snapshot as a whole.
- `release_id`, `source_url` and `release_date` identify the **publication** the
  file came from. `retrieved_at` is the download date. Mixing these up is the
  most common provenance error.
- `data_file` and every `raw_file` are paths relative to the snapshot directory
  and cannot escape it.
- `transformation_notes` records how the data file was derived; at least one
  entry is required.

Compute a hash with:

```powershell
.\.venv\Scripts\python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('raw/population_2024.xls').read_bytes()).hexdigest())"
```

Validate before opening the pull request:

```powershell
.\.venv\Scripts\python.exe -m tool_call_tr.snapshots data\snapshots
```

Error codes: `SNAPSHOT_SCHEMA_INVALID` (record does not match the schema, or a
`raw_file` is repeated), `SNAPSHOT_FILE_MISSING`, `SNAPSHOT_HASH_MISMATCH` (the
raw file changed, or the wrong hash was pasted), `SNAPSHOT_PATH_INVALID` (a path
escapes the snapshot directory), `SNAPSHOT_UNREADABLE`, and
`SNAPSHOT_SCHEMA_UNAVAILABLE` (the schema file itself cannot be read).

The conversion from the raw file to the data file is committed as
`scripts/snapshots/<domain>_<source>.py`. It must be deterministic and offline
and produce byte-identical output when re-run, so a reviewer can reproduce the
data file instead of trusting it. Name the script in `transformation_notes`.

Raw published files are committed under `raw/` because they are the evidence the
snapshot rests on. Content whose redistribution permission is unclear is not
committed; see the source and licence rules in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Output conventions

Contribution packages are written in parallel by different people, so two tools
covering the same subject can easily describe it differently. The rules below fix
the shapes that recur across packages. Follow them without coordinating with
anyone: reading this section is the coordination.

### The `source` object

A tool that answers from an official or pinned source reports where the answer
came from, using exactly these fields:

```json
"source": {
  "type": "object",
  "properties": {
    "provider": {"const": "TÜİK"},
    "dataset": {"type": "string", "minLength": 1},
    "release_id": {"type": "string", "minLength": 1},
    "source_url": {"type": "string", "format": "uri"},
    "snapshot_version": {"type": "string", "minLength": 1},
    "retrieved_at": {"type": "string", "format": "date"}
  },
  "required": ["provider", "dataset", "release_id", "source_url", "snapshot_version", "retrieved_at"],
  "additionalProperties": false
}
```

`provider` is a `const` naming the institution. The remaining values come from
the snapshot's `provenance.json`, so a reader can trace an answer back to the
published file it was derived from.

A tool serving purely synthetic fixtures has no publication to point at; it may
name its provider with a scalar `source` instead, or omit the field. But a tool
that declares a structured `source` must use this exact field set.
`test_registry.py` enforces it across every registry fragment, so a divergent
shape fails CI rather than reaching review.

### Units are never implicit

Any numeric measurement is accompanied by a `unit` field with an enumerated
value — `person`, `per_thousand`, `percent`, `mm`, and so on. A rate reported as
`8.7` with no unit is indistinguishable from `0.087`, and the two spellings will
not survive being mixed in one dataset.

### Dates, currencies, and place names

- Dates use ISO 8601 `YYYY-MM-DD` with JSON Schema `format: date`. Name the
  fields `date`, `start_date`, `end_date`.
- Currency codes are uppercase ISO 4217 in a `currency_code` field. Write `TRY`,
  never `TL` or `₺`.
- Place names are returned in the official spelling used by the source. Input
  matching is case-insensitive and tolerant of Turkish letter forms, but the
  output preserves the source's own spelling so answers stay quotable.

### Empty results

An empty answer is not a failure. Return the declared shape with nothing in it —
`{"events": [], "count": 0}` — and the execution stays `passed`. Returning
`None`, `{}` or `[]` instead makes the engine normalize the call to
`empty_result`, which is a different claim: not "there is nothing", but "the tool
produced nothing". Choose deliberately.

### Naming next to an existing tool

When a package adds a tool to a domain that already has one, the tool
descriptions must draw the boundary between them, and the pull request states it
in one sentence. Two tools that both plausibly answer "when is my exam" teach a
model to guess. The boundary is usually already implied by the package plan; the
work is writing it where the model can see it.
