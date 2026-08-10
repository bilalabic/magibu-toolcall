from __future__ import annotations

from pathlib import Path

import pytest

from tool_call_tr.cli import main
from tool_call_tr.execution import (
    ControlledStatusAdapter,
    ExecutionEngine,
    ExecutionRequest,
    ExecutionResult,
    ExecutionRouter,
    ExecutionRoutingError,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
    MockAdapter,
    StatefulSimulationAdapter,
    transition_execution_mode,
    validate_result_transfer,
)
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def registry() -> ToolRegistry:
    return ToolRegistry.load(ROOT / "registry" / "registry.jsonl")


def test_local_and_mock_execution_record_exact_mode_and_status() -> None:
    tools = registry()
    local = ExecutionEngine(tools, ExecutionRouter([LocalExecutableAdapter()]))
    result = local.execute(ExecutionRequest("call_001", "utility_add", {"left": 2, "right": 3}, ExecutionType.LOCAL_EXECUTABLE))
    assert result.status == ExecutionStatus.PASSED
    assert result.execution_type == ExecutionType.LOCAL_EXECUTABLE
    assert result.data == {"result": 5}

    mock_adapter = MockAdapter.from_registry(tools, ["utility.add.basic"])
    mock = ExecutionEngine(tools, ExecutionRouter([mock_adapter]))
    result = mock.execute(ExecutionRequest("call_002", "utility_add", {"left": 5, "right": 7}, ExecutionType.MOCK))
    assert result.status == ExecutionStatus.PASSED
    assert result.fixture_id == "utility.add.basic"


def test_no_call_timeout_rate_limit_empty_invalid_and_failure_statuses() -> None:
    assert ExecutionResult.no_call().status == ExecutionStatus.NOT_CALLED
    tools = registry()
    expected = {
        "timeout": ExecutionStatus.TIMEOUT,
        "rate_limited": ExecutionStatus.RATE_LIMITED,
        "empty": ExecutionStatus.EMPTY_RESULT,
        "invalid": ExecutionStatus.INVALID_RESULT,
        "failure": ExecutionStatus.FAILED,
    }
    for outcome, status in expected.items():
        engine = ExecutionEngine(tools, ExecutionRouter([ControlledStatusAdapter(outcome)]))
        result = engine.execute(ExecutionRequest("call_001", "utility_add", {"left": 1, "right": 2}, ExecutionType.MOCK))
        assert result.status == status


def test_real_api_never_silently_falls_back_to_mock() -> None:
    tools = registry()
    router = ExecutionRouter([MockAdapter.from_registry(tools, ["utility.add.basic"])])
    request = ExecutionRequest("call_001", "utility_add", {"left": 5, "right": 7}, ExecutionType.REAL_API)
    with pytest.raises(ExecutionRoutingError, match="explicit mode transition"):
        router.execute(request)


def test_mode_transition_is_explicit_and_recorded() -> None:
    history: list[dict] = []
    metadata = {"type": "real_api", "status": "failed"}
    request = ExecutionRequest("call_001", "utility_add", {"left": 5, "right": 7}, ExecutionType.REAL_API)
    transitioned = transition_execution_mode(request, ExecutionType.MOCK, reason="API erişimi doğrulanmadı", transformation_history=history, execution_metadata=metadata)
    assert transitioned.execution_type == ExecutionType.MOCK
    assert history == [{
        "action": "execution_mode_changed",
        "from_execution_type": "real_api",
        "to_execution_type": "mock",
        "details": "API erişimi doğrulanmadı",
    }]
    assert metadata == {"type": "mock", "status": "not_called"}


def test_declared_sequential_result_transfer() -> None:
    assert validate_result_transfer({"token": "abc"}, {"lookup_token": "abc"}, {"token": "lookup_token"}) == []
    assert validate_result_transfer({"token": "abc"}, {"lookup_token": "wrong"}, {"token": "lookup_token"}) == [
        "transfer mismatch: token -> lookup_token"
    ]


def test_stateful_simulation_can_be_reset() -> None:
    adapter = StatefulSimulationAdapter()
    put = ExecutionRequest("call_001", "simulation_put", {"key": "x", "value": 9}, ExecutionType.FULLY_SIMULATED)
    get = ExecutionRequest("call_002", "simulation_get", {"key": "x"}, ExecutionType.FULLY_SIMULATED)
    assert adapter.execute(put).status == ExecutionStatus.PASSED
    assert adapter.execute(get).data == {"value": 9}
    adapter.reset()
    assert adapter.execute(get).data == {"value": None}


def test_fixture_execution_cli(capsys) -> None:
    assert main(["tool", "run-fixture", "utility.add.basic", "--mode", "mock"]) == 0
    assert '"status": "passed"' in capsys.readouterr().out
