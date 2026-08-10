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
