from collections import Counter
import json
from pathlib import Path

import pytest

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
)
from tool_call_tr.execution.small_pilot_tools import (
    math_calculate_percentage,
    unit_convert_speed,
)
from tool_call_tr.generation.brief import build_generation_brief
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.text_quality import find_internal_operation_markers
from tool_call_tr.validation import RuleBasedValidator
from tool_call_tr.validation.parsing import parse_path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registry" / "proposals" / "registry.jsonl"
BLUEPRINT_PATH = ROOT / "blueprints" / "small_e2e_pilot.jsonl"


def _registry() -> ToolRegistry:
    return ToolRegistry.load(REGISTRY_PATH)


def _blueprints() -> list[dict]:
    parsed, issues = parse_path(BLUEPRINT_PATH)
    assert issues == []
    return [record for _, record in parsed]


def test_small_pilot_registry_and_fixtures_are_complete() -> None:
    registry = _registry()
    assert len(registry.records) == 2
    assert {record["lifecycle"] for record in registry.records} == {"candidate"}
    fixture_ids = [
        fixture_id
        for record in registry.records
        for fixture_id in record["execution"]["fixture_ids"]
    ]
    assert fixture_ids == ["math.calculate_percentage.basic", "unit.convert_speed.basic"]
    assert all(registry.load_fixture(fixture_id)["fixture_id"] == fixture_id for fixture_id in fixture_ids)


def test_small_pilot_blueprints_cover_five_categories_and_validate() -> None:
    blueprints = _blueprints()
    validator = RuleBasedValidator(registry=_registry())
    assert len(blueprints) == 5
    assert len({blueprint["id"] for blueprint in blueprints}) == 5
    assert Counter(blueprint["metadata"]["main_category"] for blueprint in blueprints) == {
        "single_tool": 1,
        "multi_tool": 1,
        "missing_parameter": 1,
        "no_tool": 1,
        "multi_turn": 1,
    }
    for blueprint in blueprints:
        assert validator.validate_record("blueprint", blueprint).valid
        serialized_brief = json.dumps(build_generation_brief(blueprint), ensure_ascii=False)
        assert not find_internal_operation_markers(serialized_brief)


def test_small_pilot_expected_calls_execute_to_oracle_results() -> None:
    registry = _registry()
    engine = ExecutionEngine(registry, ExecutionRouter([LocalExecutableAdapter()]))
    for blueprint in _blueprints():
        calls = blueprint["expected_tool_calls"]
        expected = blueprint["expected_tool_result"]
        if not calls:
            assert expected is None
            continue
        expected_results = expected if len(calls) > 1 else [expected]
        for index, (call, expected_result) in enumerate(zip(calls, expected_results, strict=True), 1):
            function = call["function"]
            result = engine.execute(ExecutionRequest(
                f"{blueprint['id']}_{index}",
                function["name"],
                function["arguments"],
                ExecutionType.LOCAL_EXECUTABLE,
            ))
            assert result.status == ExecutionStatus.PASSED
            assert result.data == expected_result


def test_small_pilot_local_tools_reject_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="percentage_out_of_range"):
        math_calculate_percentage({"value": 10, "percentage": 101})
    with pytest.raises(ValueError, match="speed_must_be_non_negative"):
        unit_convert_speed({
            "value": -1,
            "from_unit": "kilometer_per_hour",
            "to_unit": "meter_per_second",
        })
