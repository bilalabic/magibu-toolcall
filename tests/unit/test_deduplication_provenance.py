from __future__ import annotations

import copy
import json
from pathlib import Path

from tool_call_tr.deduplication import (
    DeterministicTokenSimilarity,
    combined_query_schema_hash,
    compare_records,
    exact_query_hash,
    normalize_query,
    normalized_query_hash,
    tool_schema_fingerprint,
)
from tool_call_tr.cli import main
from tool_call_tr.provenance import append_transformation, compare_provenance


ROOT = Path(__file__).resolve().parents[2]


def record() -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json").read_text(encoding="utf-8"))


def test_exact_and_normalized_hashes_are_functional() -> None:
    assert exact_query_hash("Merhaba") != exact_query_hash("merhaba")
    assert normalized_query_hash("  MERHABA, dünya! ") == normalized_query_hash("merhaba dünya")
    assert normalize_query("İSTANBUL") == "istanbul"


def test_entity_only_changes_are_flagged_as_same_scenario_shape() -> None:
    left = "Ankara için 12 Ağustos 2026 hava durumunu göster"
    right = "İzmir için 13 Ağustos 2026 hava durumunu göster"
    entities = {"city": ["Ankara", "İzmir"], "date": ["12 Ağustos 2026", "13 Ağustos 2026"]}
    assert normalized_query_hash(left, entities) == normalized_query_hash(right, entities)


def test_tool_schema_fingerprint_ignores_descriptions_but_not_structure() -> None:
    schema = record()["tools"][0]["function"]["parameters"]
    description_edit = copy.deepcopy(schema)
    description_edit["properties"]["left"]["description"] = "Değişmiş açıklama"
    assert tool_schema_fingerprint(schema) == tool_schema_fingerprint(description_edit)
    structural_edit = copy.deepcopy(schema)
    structural_edit["required"] = ["left"]
    assert tool_schema_fingerprint(schema) != tool_schema_fingerprint(structural_edit)
    assert combined_query_schema_hash("soru", [schema]) != combined_query_schema_hash("başka soru", [schema])


def test_provenance_history_and_source_comparison() -> None:
    base = record()["metadata"]["provenance"]
    updated = append_transformation(base, action="localized", actor_id="contrib_01", timestamp="2026-08-06T00:00:00+00:00")
    assert base["transformation_history"] == []
    assert updated["transformation_history"][0]["action"] == "localized"
    left = {**base, "source_dataset": "xlam", "source_example_id": "42"}
    right = {**base, "source_dataset": "xlam", "source_example_id": "42"}
    assert compare_provenance(left, right).same_source_example


def test_duplicate_report_uses_source_schema_query_and_semantic_hooks() -> None:
    left = record()
    right = copy.deepcopy(left)
    right["id"] = "tctr_ot_000099"
    assert compare_records(left, right).decision == "duplicate"
    right["messages"][0]["content"] = "Sekiz ile on ikinin toplamını bul."
    report = compare_records(left, right, semantic=DeterministicTokenSimilarity(), semantic_threshold=0.1)
    assert report.tool_schema_match
    assert report.semantic_similarity is not None
    assert report.decision == "possible_duplicate"


def test_duplicate_cli_reports_without_modifying_source(tmp_path: Path, capsys) -> None:
    left = record()
    right = copy.deepcopy(left)
    right["id"] = "tctr_ot_000099"
    path = tmp_path / "records.jsonl"
    original = "\n".join(json.dumps(item, ensure_ascii=False) for item in (left, right))
    path.write_text(original, encoding="utf-8")
    assert main(["dataset", "check-duplicates", str(path), "--output", "json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["decision"] == "duplicate"
    assert path.read_text(encoding="utf-8") == original


def test_openai_semantic_cli_requires_explicit_production_configuration(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("MAGIBU_TOOLCALL_ROOT", str(tmp_path))
    for name in ("MAGIBU_TOOLCALL_OPENAI_API_KEY", "MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)
    left = record()
    right = copy.deepcopy(left)
    right["id"] = "tctr_ot_000099"
    right["messages"][0]["content"] = "Tamamen farklı bir kullanıcı isteği."
    path = tmp_path / "records.jsonl"
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in (left, right)), encoding="utf-8")
    assert main([
        "dataset", "check-duplicates", str(path),
        "--semantic-provider", "openai",
        "--semantic-cache", str(tmp_path / "cache"),
    ]) == 1
    assert "OpenAI embedding integration is not configured" in capsys.readouterr().out
