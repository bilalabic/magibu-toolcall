# Scenario blueprint instructions

Create blueprints before candidate text. Validate each against
`schemas/scenario_blueprint.schema.json` and the registry.

Required content includes the Turkish user goal, available function names,
whether a tool is necessary, provided/missing parameters, expected decision,
expected calls/order/result, final behavior, forbidden behaviors, main category,
secondary tags, difficulty, source type, domain, intended environment,
provenance, and optional benchmark-isolation metadata.

Apply category priority exactly:

1. Two or more calls: `multi_tool`.
2. Multiple user turns and no more than one call: `multi_turn`.
3. Missing mandatory data and the example stops after asking: `missing_parameter`.
4. Direct answer or inability explanation without a call: `no_tool`.
5. One user turn and one call: `single_tool`.

For multi-tool blueprints, `execution_order=parallel` requires `parallel_tool`;
`sequential` requires `sequential_tool`. Do not place source type or difficulty
in secondary tags. Test fixtures illustrate all five categories but are not
production blueprints.

