"""Deterministic local, mock, and stateful simulation adapters."""

from __future__ import annotations

import json
from typing import Any, Callable

from tool_call_tr.execution.core import (
    ExecutionAdapter,
    ExecutionRateLimited,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTimeout,
    ExecutionType,
)
from tool_call_tr.execution.local import load_functions
from tool_call_tr.execution.simulation import SimulationTool, load_tools
from tool_call_tr.registry import ToolRegistry


def _normalized_call(
    request: ExecutionRequest,
    function: Callable[[dict[str, Any]], Any],
    *,
    fixture_id: str | None = None,
) -> ExecutionResult:
    try:
        data = function(request.arguments)
    except ExecutionTimeout as exc:
        return ExecutionResult(request.call_id, request.function_name, request.execution_type, ExecutionStatus.TIMEOUT, error=str(exc))
    except ExecutionRateLimited as exc:
        return ExecutionResult(request.call_id, request.function_name, request.execution_type, ExecutionStatus.RATE_LIMITED, error=str(exc))
    except Exception as exc:  # adapter boundary normalizes operational failures
        return ExecutionResult(request.call_id, request.function_name, request.execution_type, ExecutionStatus.FAILED, error=str(exc))
    return ExecutionResult(request.call_id, request.function_name, request.execution_type, ExecutionStatus.PASSED, data=data, fixture_id=fixture_id)


class LocalExecutableAdapter:
    execution_type = ExecutionType.LOCAL_EXECUTABLE

    def __init__(self) -> None:
        self._functions: dict[str, Callable[[dict[str, Any]], Any]] = load_functions()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match local adapter")
        function = self._functions.get(request.function_name)
        if function is None:
            return ExecutionResult(request.call_id, request.function_name, self.execution_type, ExecutionStatus.FAILED, error="local_function_not_found")
        return _normalized_call(request, function)

    def reset(self) -> None:
        return None


class MockAdapter:
    execution_type = ExecutionType.MOCK

    def __init__(self, fixtures: list[dict[str, Any]]) -> None:
        self._fixtures = {
            (fixture["function_name"], json.dumps(fixture["arguments"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))): fixture
            for fixture in fixtures
        }

    @classmethod
    def from_registry(cls, registry: ToolRegistry, fixture_ids: list[str]) -> "MockAdapter":
        return cls([registry.load_fixture(fixture_id) for fixture_id in fixture_ids])

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match mock adapter")
        key = (request.function_name, json.dumps(request.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        fixture = self._fixtures.get(key)
        if fixture is None:
            return ExecutionResult(request.call_id, request.function_name, self.execution_type, ExecutionStatus.FAILED, error="mock_fixture_not_found")
        return _normalized_call(request, lambda _: fixture["result"], fixture_id=fixture["fixture_id"])

    def reset(self) -> None:
        return None


class StatefulSimulationAdapter:
    execution_type = ExecutionType.FULLY_SIMULATED

    def __init__(self) -> None:
        self._tools = load_tools()
        self._by_function: dict[str, SimulationTool] = {
            function_name: tool for tool in self._tools for function_name in tool.function_names
        }
        self._states: dict[SimulationTool, Any] = {}
        self.reset()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match simulation adapter")
        tool = self._by_function.get(request.function_name)
        if tool is None:
            return ExecutionResult(request.call_id, request.function_name, self.execution_type, ExecutionStatus.FAILED, error="simulation_function_not_found")
        return _normalized_call(request, lambda args: tool.execute(self._states[tool], request.function_name, args))

    def reset(self) -> None:
        self._states = {tool: tool.initial_state() for tool in self._tools}


class ControlledStatusAdapter:
    """Test/example adapter for timeout, rate-limit, empty, and invalid outcomes."""

    execution_type = ExecutionType.MOCK

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        def run(_: dict[str, Any]) -> Any:
            if self.outcome == "timeout":
                raise ExecutionTimeout("fixture timeout")
            if self.outcome == "rate_limited":
                raise ExecutionRateLimited("fixture rate limit")
            if self.outcome == "empty":
                return {}
            if self.outcome == "invalid":
                return {"unexpected": True}
            raise RuntimeError("fixture failure")

        return _normalized_call(request, run)

    def reset(self) -> None:
        return None
