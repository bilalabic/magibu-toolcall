from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.cli import main
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


def test_registry_loads_a_single_json_record(tmp_path: Path) -> None:
    first_record = json.loads(
        (ROOT / "registry" / "registry.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    path = tmp_path / "utility.json"
    path.write_text(json.dumps(first_record, ensure_ascii=False), encoding="utf-8")

    registry = ToolRegistry.load(path)

    assert [record["tool_id"] for record in registry.records] == [first_record["tool_id"]]
    assert registry.fixtures_dir == tmp_path / "fixtures"


def test_registry_loads_mixed_json_and_jsonl_fragments(tmp_path: Path, capsys) -> None:
    canonical = ROOT / "registry" / "registry.jsonl"
    records = [json.loads(line) for line in canonical.read_text(encoding="utf-8").splitlines() if line]
    (tmp_path / "a-utility.json").write_text(
        json.dumps(records[0], ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "b-other-tools.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records[1:]) + "\n",
        encoding="utf-8",
    )
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "ignored.json").write_text("not a registry record", encoding="utf-8")

    registry = ToolRegistry.load(tmp_path)

    assert len(registry.records) == 3
    assert registry.fixtures_dir == fixtures
    assert main(["registry", "validate", str(tmp_path)]) == 0
    assert "OK: 3 record(s) validated" in capsys.readouterr().out


def test_registry_rejects_duplicates_across_fragment_files(tmp_path: Path) -> None:
    first_record = json.loads(
        (ROOT / "registry" / "registry.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    (tmp_path / "first.json").write_text(json.dumps(first_record), encoding="utf-8")
    (tmp_path / "second.jsonl").write_text(json.dumps(first_record) + "\n", encoding="utf-8")

    with pytest.raises(RegistryValidationError) as exc_info:
        ToolRegistry.load(tmp_path)

    codes = {issue.code for issue in exc_info.value.issues}
    assert {"DUPLICATE_TOOL_ID", "DUPLICATE_FUNCTION_NAME"} <= codes
    assert "first.json" in str(exc_info.value)
    assert "second.jsonl:1" in str(exc_info.value)


def test_registry_reports_malformed_jsonl_fragment(tmp_path: Path) -> None:
    (tmp_path / "broken.jsonl").write_text('{"tool_id":\n', encoding="utf-8")

    with pytest.raises(RegistryValidationError) as exc_info:
        ToolRegistry.load(tmp_path)

    assert exc_info.value.issues[0].code == "REGISTRY_JSON_INVALID"
    assert "broken.jsonl" in exc_info.value.issues[0].message


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
