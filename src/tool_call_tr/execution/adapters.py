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
        self._functions: dict[str, Callable[[dict[str, Any]], Any]] = {
            "utility_add": lambda args: {"result": args["left"] + args["right"]},
            "utility_multiply": lambda args: {"result": args["left"] * args["right"]},
        }

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
        self._state: dict[str, Any] = {}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match simulation adapter")
        if request.function_name == "simulation_put":
            self._state[request.arguments["key"]] = request.arguments["value"]
            return _normalized_call(request, lambda _: {"stored": True})
        if request.function_name == "simulation_get":
            return _normalized_call(request, lambda args: {"value": self._state.get(args["key"])})
        return ExecutionResult(request.call_id, request.function_name, self.execution_type, ExecutionStatus.FAILED, error="simulation_function_not_found")

    def reset(self) -> None:
        self._state.clear()


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
