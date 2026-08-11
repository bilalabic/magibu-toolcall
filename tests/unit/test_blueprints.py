from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.blueprints import (
    BenchmarkCandidateConverter,
    BlueprintError,
    BlueprintStore,
    infer_main_category,
)
from tool_call_tr.cli import main
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests" / "fixtures" / "blueprints" / "valid"


def setup() -> tuple[ToolRegistry, RuleBasedValidator]:
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    return registry, RuleBasedValidator(registry=registry)


def test_blueprint_store_loads_and_filters_all_categories() -> None:
    _, validator = setup()
    store = BlueprintStore.load_directory(VALID, validator)
    assert store.get("bp_single_tool_001")["tool_required"] is True
    assert len(store.by_category("multi_tool")) == 1
    with pytest.raises(KeyError, match="unknown blueprint"):
        store.get("missing")


def test_repository_blueprint_ids_are_unique() -> None:
    blueprint_paths = sorted((ROOT / "blueprints").rglob("*.json"))
    blueprint_paths.extend(sorted((ROOT / "blueprints").rglob("*.jsonl")))
    seen: dict[str, Path] = {}
    for path in blueprint_paths:
        records = (
            [json.loads(path.read_text(encoding="utf-8"))]
            if path.suffix == ".json"
            else [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        )
        for record in records:
            blueprint_id = record["id"]
            assert blueprint_id not in seen, (
                f"duplicate blueprint id {blueprint_id!r}: {seen[blueprint_id]} and {path}"
            )
            seen[blueprint_id] = path


@pytest.mark.parametrize(
    ("user_turns", "calls", "decision", "expected"),
    [
        (1, 2, "tool_call", "multi_tool"),
        (2, 1, "tool_call", "multi_turn"),
        (1, 0, "request_information", "missing_parameter"),
        (1, 0, "direct_answer", "no_tool"),
        (1, 1, "tool_call", "single_tool"),
    ],
)
def test_category_priority(user_turns: int, calls: int, decision: str, expected: str) -> None:
    assert infer_main_category(user_turns=user_turns, tool_call_count=calls, decision=decision) == expected


def test_invalid_blueprint_directory_stops_loading(tmp_path: Path) -> None:
    _, validator = setup()
    invalid = ROOT / "tests" / "fixtures" / "blueprints" / "invalid" / "invalid_multi_tool.json"
    (tmp_path / "invalid.json").write_text(invalid.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(BlueprintError) as exc_info:
        BlueprintStore.load_directory(tmp_path, validator)
    assert exc_info.value.issues


def test_blueprint_store_loads_mixed_json_and_jsonl_files(tmp_path: Path) -> None:
    _, validator = setup()
    single_tool = (VALID / "single_tool.json").read_text(encoding="utf-8")
    no_tool = json.loads((VALID / "no_tool.json").read_text(encoding="utf-8"))
    (tmp_path / "single.json").write_text(single_tool, encoding="utf-8")
    (tmp_path / "other.jsonl").write_text(
        json.dumps(no_tool, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    store = BlueprintStore.load_directory(tmp_path, validator)

    assert store.get("bp_single_tool_001")["expected_behavior"] == "tool_call"
    assert store.get("bp_no_tool_001")["expected_behavior"] == "direct_answer"


def test_blueprint_store_rejects_duplicate_ids_across_formats(tmp_path: Path) -> None:
    _, validator = setup()
    blueprint = (VALID / "single_tool.json").read_text(encoding="utf-8")
    (tmp_path / "first.json").write_text(blueprint, encoding="utf-8")
    (tmp_path / "second.jsonl").write_text(
        json.dumps(json.loads(blueprint), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BlueprintError, match="duplicate blueprint ID") as exc_info:
        BlueprintStore.load_directory(tmp_path, validator)

    assert "first.json" in str(exc_info.value)
    assert "second.jsonl:1" in str(exc_info.value)


def test_blueprint_cli_validates_a_mixed_directory_and_rejects_duplicate_ids(
    tmp_path: Path,
    capsys,
) -> None:
    registry_path = ROOT / "registry" / "registry.jsonl"
    single_tool = json.loads((VALID / "single_tool.json").read_text(encoding="utf-8"))
    no_tool = (VALID / "no_tool.json").read_text(encoding="utf-8")
    (tmp_path / "first.json").write_text(no_tool, encoding="utf-8")
    (tmp_path / "second.jsonl").write_text(
        json.dumps(single_tool, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert main(["blueprint", "validate", str(tmp_path), "--registry", str(registry_path)]) == 0
    assert "OK: 2 record(s) validated" in capsys.readouterr().out

    (tmp_path / "duplicate.jsonl").write_text(
        json.dumps(single_tool, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert main(["blueprint", "validate", str(tmp_path), "--registry", str(registry_path)]) == 1
    assert "DUPLICATE_BLUEPRINT_ID" in capsys.readouterr().out


def test_benchmark_candidate_conversion_remains_review_required() -> None:
    registry, validator = setup()
    blueprint = json.loads((VALID / "single_tool.json").read_text(encoding="utf-8"))
    candidate = BenchmarkCandidateConverter(registry).convert(
        blueprint,
        record_id="bench_ot_000010",
        user_message="On iki ile sekizi toplar mısın?",
    )
    assert candidate["metadata"]["review"]["status"] == "needs_revision"
    assert candidate["expected"]["decision"] == "tool_call"
    assert candidate["messages"] == [{"role": "user", "content": "On iki ile sekizi toplar mısın?"}]
    assert validator.validate_record("benchmark", candidate).valid
