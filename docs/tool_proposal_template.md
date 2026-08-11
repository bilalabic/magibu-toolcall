# Tool proposal template

Use this worksheet before adding a new contributor-owned `.json` or `.jsonl`
fragment under `registry/proposals/`. Do not edit a shared proposal aggregate.
The worksheet gathers the human research needed
to write a machine-valid registry record; it does not replace
`schemas/tool_registry.schema.json`.

Proposals remain `candidate` until source, license, execution, and safety review
is complete. Use `demo` only for repository test tools. A successful schema
validation is not approval for live access or redistribution.

```text
Tool name:
Tool ID (<domain>.<action>.v<major>):
Function name (<domain>_<action>):
Purpose and domain:
API/data source and URL:
Input schema:
Output schema:
Required parameters:
Optional parameters:
Turkish example request:
Expected tool call:
Missing-information behavior:
Do-not-use boundary:
Default and supported execution environments:
Fixture IDs / reproducibility plan:
Authentication and credential environment variables:
License, license URL, and terms check date:
Safety, personal-data, and side-effect risks:
Freshness/stability risks:
Proposer and review notes:
```

The registry loader meta-validates input/output schemas, checks tool/function
names, domain and major-version agreement, supported default execution, and
duplicate tool IDs/function names.

Submit the registry record together with the implementation appropriate to its
declared mode:

- `local_executable`: registered deterministic function and tests;
- `mock`: referenced schema-valid fixture with explicit provenance;
- `fully_simulated`: resettable stateful adapter and transition tests;
- `real_api`: reviewed HTTPS GET contract, allowlisted host, auth environment
  variable names, normalization behavior, and error tests;
- `sandbox`: adapter and isolation tests, because no runnable sandbox exists yet.

Do not add secrets, real personal data, undocumented endpoints, or a live
side-effecting operation to a proposal.
