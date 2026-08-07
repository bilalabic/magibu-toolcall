from collections import Counter
import json
from pathlib import Path

from tool_call_tr.dataset_workflow import build_candidate_from_language_plan, prepare_generated_candidate
from tool_call_tr.generation.providers import ModelIdentity
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator
from tool_call_tr.validation.parsing import parse_path


ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_PATHS = (
    ROOT / "blueprints" / "pilot_general.jsonl",
    ROOT / "blueprints" / "pilot_turkey_native.jsonl",
)
REGRESSION_PATH = ROOT / "blueprints" / "regressions" / "parcel_natural_v2.jsonl"


def _registry() -> ToolRegistry:
    return ToolRegistry.load(ROOT / "registry" / "proposals" / "pilot_candidates.jsonl")


def _blueprints() -> list[dict]:
    records = []
    for path in BLUEPRINT_PATHS:
        parsed, issues = parse_path(path)
        assert issues == []
        records.extend(record for _, record in parsed)
    return records


def _fixture_index(registry: ToolRegistry) -> dict[tuple[str, str], dict]:
    fixtures = {}
    for tool in registry.records:
        for fixture_id in tool["execution"]["fixture_ids"]:
            fixture = registry.load_fixture(fixture_id)
            key = (
                fixture["function_name"],
                json.dumps(fixture["arguments"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            fixtures[key] = fixture
    return fixtures


def test_pilot_blueprints_are_valid_and_balanced() -> None:
    registry = _registry()
    validator = RuleBasedValidator(registry=registry)
    blueprints = _blueprints()
    assert len(blueprints) == 30
    assert len({blueprint["id"] for blueprint in blueprints}) == 30
    for blueprint in blueprints:
        assert validator.validate_record("blueprint", blueprint).valid

    assert Counter(item["metadata"]["source_type"] for item in blueprints) == {
        "original_turkish": 15,
        "turkey_native": 15,
    }
    assert Counter(item["metadata"]["main_category"] for item in blueprints) == {
        "single_tool": 16,
        "multi_turn": 3,
        "missing_parameter": 4,
        "no_tool": 2,
        "multi_tool": 5,
    }
    assert Counter(item["metadata"]["difficulty"] for item in blueprints) == {
        "easy": 14,
        "medium": 12,
        "hard": 4,
    }


def test_every_expected_call_matches_a_fixture_and_declared_mode() -> None:
    registry = _registry()
    fixtures = _fixture_index(registry)
    used_functions: set[str] = set()
    for blueprint in _blueprints():
        calls = blueprint["expected_tool_calls"]
        expected_results = blueprint["expected_tool_result"]
        if not calls:
            assert expected_results is None
            assert blueprint["metadata"]["intended_execution_type"] == "not_applicable"
            continue
        results = expected_results if len(calls) > 1 else [expected_results]
        for call, expected_result in zip(calls, results, strict=True):
            function = call["function"]
            used_functions.add(function["name"])
            key = (
                function["name"],
                json.dumps(function["arguments"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            assert key in fixtures
            assert expected_result == fixtures[key]["result"]
            tool = registry.by_function_name(function["name"])
            assert blueprint["metadata"]["intended_execution_type"] == tool["execution"]["default_type"]

    assert used_functions == {tool["function"]["name"] for tool in registry.records}


def test_machine_controlled_assembly_builds_all_30_dataset_records() -> None:
    registry = _registry()
    validator = RuleBasedValidator(registry=registry)
    source_counters = Counter()
    for blueprint in _blueprints():
        source_type = blueprint["metadata"]["source_type"]
        source_counters[source_type] += 1
        prefix = "ot" if source_type == "original_turkish" else "tn"
        record_id = f"tctr_{prefix}_{source_counters[source_type]:06d}"
        multi_turn = blueprint["metadata"]["main_category"] == "multi_turn"
        plan = {
            "user_messages": (
                ["İlk isteğim bu.", "Gerekli ayrıntıyı şimdi paylaşıyorum."]
                if multi_turn
                else [blueprint["user_goal"]]
            ),
            "intermediate_assistant_response": (
                "Gerekli ayrıntıyı paylaşır mısınız?" if multi_turn else None
            ),
            "final_response": "İstenen sonucu araç çıktısına dayanarak paylaşıyorum.",
        }
        candidate = build_candidate_from_language_plan(
            plan,
            blueprint=blueprint,
            record_id=record_id,
            registry=registry,
        )
        prepared = prepare_generated_candidate(
            candidate,
            blueprint=blueprint,
            record_id=record_id,
            identity=ModelIdentity("fake", "fixture-model", "v1", "dataset_language_generator"),
            actor_id="dataset_operator_01",
            generated_at="2026-08-07T00:00:00+00:00",
        )
        assert validator.validate_record("dataset", prepared).valid


def test_parcel_natural_v2_regression_blueprint_is_valid_and_versioned() -> None:
    registry = _registry()
    validator = RuleBasedValidator(registry=registry)
    parsed, issues = parse_path(REGRESSION_PATH)

    assert issues == []
    assert len(parsed) == 1
    blueprint = parsed[0][1]
    assert blueprint["id"] == "bp_native_parcel_natural_009"
    assert blueprint["metadata"]["provenance"]["source_split"] == "pilot-regression"
    assert validator.validate_record("blueprint", blueprint).valid
    assert "ISO zaman damgalarını ham biçimde aktarmak." in blueprint["must_avoid"]
    assert "Olay konumlarını atlamak." in blueprint["must_avoid"]
