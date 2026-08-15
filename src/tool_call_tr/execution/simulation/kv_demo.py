"""Reference `fully_simulated` module: an in-memory key/value store."""

from __future__ import annotations

from typing import Any

from tool_call_tr.execution.simulation import SimulationTool


class KeyValueStoreTool:
    """Stores and reads values in a state that `reset()` empties again."""

    function_names = ("simulation_put", "simulation_get")

    def initial_state(self) -> dict[str, Any]:
        return {}

    def execute(self, state: dict[str, Any], function_name: str, arguments: dict[str, Any]) -> Any:
        if function_name == "simulation_put":
            state[arguments["key"]] = arguments["value"]
            return {"stored": True}
        return {"value": state.get(arguments["key"])}


TOOLS: tuple[SimulationTool, ...] = (KeyValueStoreTool(),)
