# Scenario blueprint instructions

A blueprint is the machine-validated plan for one dataset example. It is written
before model generation and describes the intended problem, available tools,
expected calls, result, and final behavior. It is not a generated conversation
and it is not automatically accepted dataset data.

The authoritative structural contract is
`schemas/scenario_blueprint.schema.json`. Cross-field and registry rules are
implemented by the Python validator.

## Required concepts

| Field group | What it describes |
| --- | --- |
| Identity | `schema_version`, `tool_registry_version`, and a unique `bp_*` ID |
| User intent | A natural Turkish `user_goal` without internal operation labels |
| Tool context | `available_tools`, whether a tool is required, and the provided or missing parameters |
| Expected decision | Tool call, direct answer, request for information, or inability to answer |
| Oracle | Expected calls, call order, tool result, final behavior, and forbidden behavior |
| Coverage | Main category, secondary tags, difficulty, source type, domain, and intended execution type |
| Provenance | Source references, transformations, generator identity when applicable, and license chain |

Function names and parameter keys remain in their stable English machine form.
The user goal, final-behavior requirement, and forbidden behaviors use natural
Türkiye Turkish.

## Expected behavior rules

| `expected_behavior` | Required shape |
| --- | --- |
| `tool_call` | `tool_required=true`, at least one expected call, and no missing parameter |
| `request_information` | No expected call, at least one missing parameter, and `execution_order=not_applicable` |
| `direct_answer` | No required tool, no call, and no missing parameter |
| `cannot_answer` | No required tool or call; explain the capability/policy boundary |

Every expected function must appear in `available_tools` and in the registry used
for validation. Expected arguments and results must satisfy that tool's input and
output schemas.

## Main-category priority

Assign exactly one main category using this order. Stop at the first matching
rule:

1. Two or more calls: `multi_tool`.
2. Multiple user turns and no more than one call: `multi_turn`.
3. Required information is missing and the example stops after asking:
   `missing_parameter`.
4. The correct behavior is a direct answer or inability explanation without a
   call: `no_tool`.
5. One user turn and one call: `single_tool`.

For `multi_tool`, `execution_order=parallel` requires the `parallel_tool`
secondary tag; `execution_order=sequential` requires `sequential_tool`. Do not
repeat source type or difficulty in `secondary_tags`.

## Authoring checklist

Before submitting a blueprint, confirm that:

- the ID is unique across every file under `blueprints/`;
- only active source types are used for active dataset production;
- distractor tools are realistic but do not make the oracle ambiguous;
- missing values are not guessed or copied from information unavailable at that
  turn;
- sequential calls explicitly transfer the prior result into the next call;
- `expected_tool_result` satisfies the selected tool's output schema;
- `expected_final_behavior` states what must be communicated, not exact prose;
- `must_avoid` covers unsupported claims, unsafe effects, and likely tool-choice
  mistakes;
- the execution type matches the registry contract;
- operational words such as synthetic, fixture, mock, validation, or review do
  not leak into natural user/assistant text unless the scenario explicitly
  discusses that concept.

## Validation

Use the registry that owns the referenced functions. The first command below is
an immediately runnable infrastructure check. The second pattern validates a
proposal-backed blueprint against all contributor-owned registry fragments:

```powershell
.\.venv\Scripts\magibu-toolcall.exe blueprint validate tests\fixtures\blueprints\valid\single_tool.json --registry registry\registry.jsonl
$ProposalRegistry = "registry\proposals"
$BlueprintFile = "blueprints\contribution.jsonl"
.\.venv\Scripts\magibu-toolcall.exe blueprint validate $BlueprintFile --registry $ProposalRegistry
```

Repository'ye eklenen blueprint katkıları yalnız `.jsonl` biçimindedir ve her
satırda bir blueprint kaydı bulunur. Dosya yolu
`blueprints/<domain>_<source>.jsonl` düzenini izler. `tests/fixtures/` altındaki
`.json` dosyaları yalnız test amaçlıdır.

The test suite also checks repository-wide blueprint ID uniqueness. Files under
`tests/fixtures/blueprints/` demonstrate validator cases; they are not production
blueprints.
