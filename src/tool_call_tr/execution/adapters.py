"""Deterministic local, mock, and stateful simulation adapters."""

from __future__ import annotations

from datetime import datetime
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
from tool_call_tr.execution.local_tools import LOCAL_PILOT_FUNCTIONS
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
            **LOCAL_PILOT_FUNCTIONS,
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
        self._calendar_seed = [{
            "event_id": "SYN-EVENT-001",
            "title": "Proje değerlendirme toplantısı",
            "start_datetime": "2026-08-10T10:00:00+03:00",
            "end_datetime": "2026-08-10T10:45:00+03:00",
            "location": "Sentetik toplantı odası",
        }]
        self._calendar_events: list[dict[str, Any]] = []
        self._next_calendar_id = 2
        self.reset()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match simulation adapter")
        if request.function_name == "simulation_put":
            self._state[request.arguments["key"]] = request.arguments["value"]
            return _normalized_call(request, lambda _: {"stored": True})
        if request.function_name == "simulation_get":
            return _normalized_call(request, lambda args: {"value": self._state.get(args["key"])})
        if request.function_name == "calendar_list_events":
            return _normalized_call(request, self._calendar_list_events)
        if request.function_name == "calendar_create_event":
            return _normalized_call(request, self._calendar_create_event)
        return ExecutionResult(request.call_id, request.function_name, self.execution_type, ExecutionStatus.FAILED, error="simulation_function_not_found")

    def reset(self) -> None:
        self._state.clear()
        self._calendar_events = [event.copy() for event in self._calendar_seed]
        self._next_calendar_id = 2

    def _calendar_list_events(self, arguments: dict[str, Any]) -> dict[str, Any]:
        start = _aware_datetime(arguments["start_datetime"])
        end = _aware_datetime(arguments["end_datetime"])
        if end <= start:
            raise ValueError("calendar_range_must_end_after_start")
        query = arguments.get("query", "").casefold()
        events = []
        for event in self._calendar_events:
            event_start = _aware_datetime(event["start_datetime"])
            event_end = _aware_datetime(event["end_datetime"])
            if event_start < end and event_end > start and (not query or query in event["title"].casefold()):
                events.append(event.copy())
        return {"events": events}

    def _calendar_create_event(self, arguments: dict[str, Any]) -> dict[str, Any]:
        start = _aware_datetime(arguments["start_datetime"])
        end = _aware_datetime(arguments["end_datetime"])
        if end <= start:
            raise ValueError("calendar_event_must_end_after_start")
        if not arguments["confirmed"]:
            return {"event_id": None, "status": "confirmation_required"}
        event_id = f"SYN-EVENT-{self._next_calendar_id:03d}"
        self._next_calendar_id += 1
        self._calendar_events.append({
            "event_id": event_id,
            "title": arguments["title"],
            "start_datetime": start.isoformat(),
            "end_datetime": end.isoformat(),
            "location": arguments.get("location"),
        })
        return {"event_id": event_id, "status": "created"}


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid_datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("calendar_datetime_requires_utc_offset")
    return parsed


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
