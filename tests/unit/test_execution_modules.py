from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tool_call_tr.execution import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
    StatefulSimulationAdapter,
)
from tool_call_tr.execution.local import LocalModuleError, load_functions, module_names
from tool_call_tr.execution.simulation import SimulationModuleError, load_tools

LOCAL_MODULE = """
FUNCTIONS = {"demo_echo": lambda arguments: {"result": arguments["value"]}}
"""

SIMULATION_MODULE = """
class _CounterTool:
    function_names = ("demo_count",)

    def initial_state(self):
        return {"calls": 0}

    def execute(self, state, function_name, arguments):
        state["calls"] += 1
        return {"calls": state["calls"]}


TOOLS = (_CounterTool(),)
"""


def write_package(root: Path, name: str, modules: dict[str, str]) -> str:
    """Create an importable package next to `root` and return its import name."""

    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for module_name, source in modules.items():
        (package / f"{module_name}.py").write_text(source, encoding="utf-8")
    importlib.invalidate_caches()
    return name


def test_local_functions_are_discovered_in_deterministic_order() -> None:
    functions = load_functions()
    assert module_names() == sorted(module_names())
    assert list(functions) == list(load_functions())
    assert {"utility_add", "utility_multiply"} <= set(functions)


def test_moved_demo_functions_keep_their_behavior() -> None:
    functions = load_functions()
    assert functions["utility_add"]({"left": 2, "right": 3}) == {"result": 5}
    assert functions["utility_multiply"]({"left": 2, "right": 3}) == {"result": 6}

    adapter = LocalExecutableAdapter()
    request = ExecutionRequest("call_001", "utility_add", {"left": 12, "right": 8}, ExecutionType.LOCAL_EXECUTABLE)
    result = adapter.execute(request)
    assert result.status == ExecutionStatus.PASSED
    assert result.data == {"result": 20}

    unknown = ExecutionRequest("call_002", "utility_unknown", {}, ExecutionType.LOCAL_EXECUTABLE)
    assert adapter.execute(unknown).error == "local_function_not_found"


def test_duplicate_local_function_names_fail_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(tmp_path)
    package = write_package(tmp_path, "duplicate_local_pkg", {"demo_first": LOCAL_MODULE, "demo_second": LOCAL_MODULE})
    with pytest.raises(LocalModuleError, match="duplicate local function 'demo_echo'.*demo_first.*demo_second"):
        load_functions(package)


def test_local_module_without_functions_mapping_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(tmp_path)
    package = write_package(tmp_path, "empty_local_pkg", {"demo_missing": "VALUE = 1\n"})
    with pytest.raises(LocalModuleError, match="FUNCTIONS"):
        load_functions(package)


def test_simulation_tools_are_discovered_and_own_their_function_names() -> None:
    functions = {name for tool in load_tools() for name in tool.function_names}
    assert {"simulation_put", "simulation_get"} <= functions


def test_simulation_reset_restores_the_initial_state() -> None:
    adapter = StatefulSimulationAdapter()
    put = ExecutionRequest("call_001", "simulation_put", {"key": "x", "value": 9}, ExecutionType.FULLY_SIMULATED)
    get = ExecutionRequest("call_002", "simulation_get", {"key": "x"}, ExecutionType.FULLY_SIMULATED)

    assert adapter.execute(put).data == {"stored": True}
    assert adapter.execute(get).data == {"value": 9}

    adapter.reset()
    assert adapter.execute(get).data == {"value": None}

    assert adapter.execute(put).data == {"stored": True}
    assert adapter.execute(get).data == {"value": 9}


def test_unknown_simulation_function_fails_without_fallback() -> None:
    adapter = StatefulSimulationAdapter()
    request = ExecutionRequest("call_001", "simulation_unknown", {}, ExecutionType.FULLY_SIMULATED)
    result = adapter.execute(request)
    assert result.status == ExecutionStatus.FAILED
    assert result.error == "simulation_function_not_found"


def test_duplicate_simulation_function_names_fail_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(tmp_path)
    package = write_package(tmp_path, "duplicate_sim_pkg", {"demo_a": SIMULATION_MODULE, "demo_b": SIMULATION_MODULE})
    with pytest.raises(SimulationModuleError, match="duplicate simulation function 'demo_count'.*demo_a.*demo_b"):
        load_tools(package)


def test_simulation_module_without_tools_sequence_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(tmp_path)
    package = write_package(tmp_path, "empty_sim_pkg", {"demo_missing": "VALUE = 1\n"})
    with pytest.raises(SimulationModuleError, match="TOOLS"):
        load_tools(package)


def test_registered_simulation_tools_keep_independent_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(tmp_path)
    package = write_package(tmp_path, "counter_sim_pkg", {"demo_counter": SIMULATION_MODULE})
    tool = load_tools(package)[0]
    state = tool.initial_state()

    assert tool.execute(state, "demo_count", {}) == {"calls": 1}
    assert tool.execute(tool.initial_state(), "demo_count", {}) == {"calls": 1}
