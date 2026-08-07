from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tool_call_tr.cli import main
from tool_call_tr.localization import LocalizationError, apply_localization
from tool_call_tr.schemas import SchemaStore
from tool_call_tr.sources import SourceIngestionError, XlamAdapter, When2CallAdapter, machine_fingerprint


ROOT = Path(__file__).resolve().parents[2]


def xlam_row() -> dict:
    return {
        "id": 42,
        "query": "Add two and three.",
        "tools": json.dumps([{
            "name": "math.add",
            "description": "Add two numbers.",
            "parameters": {
                "left": {"type": "int", "description": "First number.", "required": True},
                "right": {"type": "int", "description": "Second number.", "required": True},
            },
        }]),
        "answers": json.dumps([{"name": "math.add", "arguments": {"left": 2, "right": 3}}]),
    }


def localization_patch() -> dict:
    return {
        "source_example_id": "42",
        "query": "İki ile üçü topla.",
        "tool_descriptions": {"math.add": "İki sayıyı toplar."},
        "parameter_descriptions": {"math.add": {"left": "İlk sayı.", "right": "İkinci sayı."}},
        "response": None,
        "actor_id": "dataset_operator_01",
        "provider": "human",
        "provider_version": None,
    }


def test_xlam_real_shape_and_stringified_json_are_normalized() -> None:
    item = XlamAdapter(terms_accepted=True).convert(xlam_row(), row_number=1, source_file="xlam.json", split="train")
    SchemaStore(ROOT / "schemas").validate("source", item)
    assert item["source"]["dataset"] == "Salesforce/xlam-function-calling-60k"
    assert item["source"]["license"] == "cc-by-4.0"
    assert item["content"]["tools"][0]["parameters"]["required"] == ["left", "right"]
    assert item["content"]["tools"][0]["parameters"]["properties"]["left"]["type"] == "integer"
    assert item["content"]["tool_calls"][0]["name"] == "math.add"


def test_xlam_terms_cannot_be_bypassed() -> None:
    with pytest.raises(SourceIngestionError, match="terms"):
        XlamAdapter(terms_accepted=False)


def test_when2call_test_shape_maps_decisions_and_missing_parameter() -> None:
    row = {
        "uuid": "w2c-1",
        "question": "Find weather.",
        "correct_answer": "request_for_info",
        "answers": {
            "direct": "No.", "tool_call": "{}",
            "request_for_info": "Which city?", "cannot_answer": "Cannot.",
        },
        "target_tool": None,
        "tools": [json.dumps({
            "name": "weather_get", "description": "Weather.",
            "parameters": {"type": "dict", "required": ["city"], "properties": {"city": {"type": "str", "description": "City."}}},
        })],
        "held_out_param": "city",
    }
    item = When2CallAdapter().convert(row, row_number=1, source_file="when2call.jsonl", split="test")
    SchemaStore(ROOT / "schemas").validate("source", item)
    assert item["content"]["decision"] == "request_information"
    assert item["content"]["missing_parameters"] == ["city"]
    assert item["source"]["format"] == "when2call_test"


def test_localization_changes_only_natural_language_fields() -> None:
    item = XlamAdapter(terms_accepted=True).convert(xlam_row(), row_number=1, source_file="xlam.json", split="train")
    localized = apply_localization(item, localization_patch(), timestamp="2026-08-06T00:00:00+00:00")
    SchemaStore(ROOT / "schemas").validate("source", localized)
    assert localized["localized_content"]["query"] == "İki ile üçü topla."
    assert localized["localized_content"]["tools"][0]["name"] == "math.add"
    assert machine_fingerprint(localized["localized_content"]) == item["localization"]["machine_fingerprint"]
    assert localized["localization"]["status"] == "localized_needs_review"


def test_localization_rejects_machine_name_changes() -> None:
    item = XlamAdapter(terms_accepted=True).convert(xlam_row(), row_number=1, source_file="xlam.json", split="train")
    patch = localization_patch()
    patch["tool_descriptions"] = {"math.topla": "Toplar."}
    with pytest.raises(LocalizationError, match="exactly match"):
        apply_localization(item, patch)


def test_source_cli_import_validate_and_localize(tmp_path: Path, capsys, access_files) -> None:
    raw = tmp_path / "xlam.jsonl"
    imported = tmp_path / "imported.jsonl"
    patches = tmp_path / "patches.jsonl"
    localized = tmp_path / "localized.jsonl"
    raw.write_text(json.dumps(xlam_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    patches.write_text(json.dumps(localization_patch(), ensure_ascii=False) + "\n", encoding="utf-8")

    access = ["--actor-id", "dataset_operator_01", "--policy", access_files["policy"], "--audit-log", access_files["audit"]]
    assert main(["dataset", "source", "import", str(raw), str(imported), "--source", "xlam", "--split", "train", *access]) == 1
    assert "source-terms acceptance" in capsys.readouterr().out
    assert main([
        "dataset", "source", "import", str(raw), str(imported), "--source", "xlam", "--split", "train",
        "--source-terms-accepted",
        *access,
    ]) == 0
    capsys.readouterr()
    assert main(["dataset", "source", "validate", str(imported)]) == 0
    capsys.readouterr()
    assert main([
        "dataset", "source", "localize", str(imported), str(patches), str(localized),
        "--timestamp", "2026-08-06T00:00:00+00:00",
        *access,
    ]) == 0
    capsys.readouterr()
    value = json.loads(localized.read_text(encoding="utf-8").splitlines()[0])
    assert value["localized_content"]["query"] == "İki ile üçü topla."

    manifest = tmp_path / "import-job.json"
    job_output = tmp_path / "job-imported.jsonl"
    assert main([
        "dataset", "batch", "plan", str(raw), str(manifest),
        "--job-id", "xlam-import-001", "--operation", "source_import",
        "--output", str(job_output), "--checkpoint", str(tmp_path / "import-checkpoint.json"),
        "--errors", str(tmp_path / "import-errors.jsonl"), "--shard-size", "1", *access,
    ]) == 0
    capsys.readouterr()
    assert main([
        "dataset", "source", "import-job", str(manifest), "--source", "xlam", "--split", "train",
        "--source-terms-accepted", *access,
    ]) == 0
    capsys.readouterr()
    assert json.loads(job_output.read_text(encoding="utf-8"))["source"]["example_id"] == "42"
