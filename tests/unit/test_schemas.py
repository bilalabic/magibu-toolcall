from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from tool_call_tr.cli import main
from tool_call_tr.schemas import SCHEMA_FILES, SchemaStore, json_path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_required_schemas_are_valid_draft_2020_12() -> None:
    store = SchemaStore(ROOT / "schemas")
    assert set(SCHEMA_FILES) == {"dataset", "benchmark", "registry", "blueprint", "source", "job"}
    for kind in SCHEMA_FILES:
        assert store.load(kind)["$schema"].endswith("2020-12/schema")


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("dataset", FIXTURES / "dataset" / "valid_single_tool.json"),
        ("benchmark", FIXTURES / "benchmark" / "valid_tool_call.json"),
        ("registry", FIXTURES / "registry" / "valid_tool.json"),
    ],
)
def test_valid_schema_fixtures(kind: str, path: Path) -> None:
    SchemaStore(ROOT / "schemas").validate(kind, load(path))


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("dataset", FIXTURES / "dataset" / "invalid_record.json"),
        ("benchmark", FIXTURES / "benchmark" / "invalid_expected.json"),
        ("registry", FIXTURES / "registry" / "invalid_tool.json"),
        ("blueprint", FIXTURES / "blueprints" / "invalid" / "invalid_multi_tool.json"),
    ],
)
def test_invalid_schema_fixtures(kind: str, path: Path) -> None:
    errors = SchemaStore(ROOT / "schemas").errors(kind, load(path))
    assert errors
    assert json_path(errors[0]).startswith("$")
    with pytest.raises(ValidationError):
        SchemaStore(ROOT / "schemas").validate(kind, load(path))


def test_one_valid_blueprint_per_main_category() -> None:
    store = SchemaStore(ROOT / "schemas")
    categories = set()
    for path in (FIXTURES / "blueprints" / "valid").glob("*.json"):
        record = load(path)
        store.validate("blueprint", record)
        categories.add(record["metadata"]["main_category"])
    assert categories == {"single_tool", "no_tool", "missing_parameter", "multi_turn", "multi_tool"}


def test_schema_cli_has_meaningful_exit_codes_and_json_output(capsys) -> None:
    valid = FIXTURES / "dataset" / "valid_single_tool.json"
    invalid = FIXTURES / "dataset" / "invalid_record.json"
    assert main(["dataset", "validate", str(valid)]) == 0
    assert "OK:" in capsys.readouterr().out
    assert main(["dataset", "validate", str(invalid), "--output", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["issues"][0]["code"].startswith("SCHEMA_")
    assert report["issues"][0]["severity"] == "error"
