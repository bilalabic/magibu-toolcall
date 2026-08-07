from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.registry import RegistryValidationError, ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_registry_load_lookup_and_demo_lifecycle() -> None:
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    assert len(registry.records) == 3
    assert registry.by_tool_id("utility.add.v1")["function"]["name"] == "utility_add"
    assert registry.by_function_name("weather_get_forecast")["tool_id"] == "weather.get_forecast.v1"
    assert {record["lifecycle"] for record in registry.records} == {"demo"}
    with pytest.raises(KeyError, match="unknown function"):
        registry.by_function_name("missing_tool")


def test_registry_fixed_fixture_is_declared_and_schema_valid() -> None:
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    fixture = registry.load_fixture("utility.add.basic")
    assert fixture["result"] == {"result": 12}


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda records: records.append(records[0].copy()), "DUPLICATE_TOOL_ID"),
        (lambda records: records.append({**records[1], "tool_id": "utility.other.v1"}), "DUPLICATE_FUNCTION_NAME"),
        (lambda records: records[0]["execution"].update(default_type="sandbox"), "DEFAULT_EXECUTION_NOT_SUPPORTED"),
        (lambda records: records[0].update(tool_version="2.0.0"), "TOOL_MAJOR_MISMATCH"),
    ],
)
def test_registry_semantic_failures(tmp_path: Path, mutation, code: str) -> None:
    source = ROOT / "registry" / "registry.jsonl"
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    mutation(records)
    path = tmp_path / "registry.jsonl"
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")
    with pytest.raises(RegistryValidationError) as exc_info:
        ToolRegistry.load(path)
    assert code in {issue.code for issue in exc_info.value.issues}
