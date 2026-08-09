from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.batch import BatchError
from tool_call_tr.dataset_workflow import (
    DatasetWorkflowError,
    build_candidate_from_language_plan,
    collect_dataset_existing_ids,
    default_job_paths,
    inspect_blueprints,
    next_dataset_number,
    prepare_generated_candidate,
)
from tool_call_tr.generation.providers import ModelIdentity
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_blueprint_preflight_derives_frozen_quality_distribution() -> None:
    path = ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json"
    plan = inspect_blueprints(path)
    assert plan.total_items == 1
    assert plan.source_type == "original_turkish"
    assert plan.target_distributions == {
        "main_category": {"no_tool": 1},
        "source_type": {"original_turkish": 1},
        "domain": {"general": 1},
        "difficulty": {"easy": 1},
    }


def test_blueprint_preflight_blocks_paused_translation(tmp_path: Path) -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    blueprint["metadata"]["source_type"] = "translated"
    path = tmp_path / "translated.json"
    path.write_text(json.dumps(blueprint), encoding="utf-8")
    with pytest.raises(DatasetWorkflowError, match="translation is paused"):
        inspect_blueprints(path)


def test_next_dataset_number_is_scoped_by_source_type() -> None:
    assert next_dataset_number({"tctr_ot_000004", "tctr_tn_000099"}, "original_turkish") == 5
    assert next_dataset_number({"tctr_ot_000004", "tctr_tn_000099"}, "turkey_native") == 100


def test_existing_id_collection_allows_audit_copies_across_lifecycle_states(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "dataset" / "staging" / "candidate.jsonl"
    revision = tmp_path / "data" / "dataset" / "needs_revision" / "candidate.jsonl"
    staging.parent.mkdir(parents=True)
    revision.parent.mkdir(parents=True)
    staging.write_text('{"id":"tctr_tn_000001"}\n', encoding="utf-8")
    revision.write_text('{"id":"tctr_tn_000001"}\n', encoding="utf-8")

    assert collect_dataset_existing_ids(tmp_path) == {"tctr_tn_000001"}


def test_existing_id_collection_rejects_duplicates_within_one_lifecycle_state(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "dataset" / "staging"
    staging.mkdir(parents=True)
    (staging / "first.jsonl").write_text('{"id":"tctr_ot_000001"}\n', encoding="utf-8")
    (staging / "second.jsonl").write_text('{"id":"tctr_ot_000001"}\n', encoding="utf-8")

    with pytest.raises(BatchError, match="occurs more than once"):
        collect_dataset_existing_ids(tmp_path)


def test_job_id_cannot_escape_the_runs_directory(tmp_path: Path) -> None:
    with pytest.raises(DatasetWorkflowError, match="job_id"):
        default_job_paths(
            project_root=tmp_path,
            runs_dir=tmp_path / "runs",
            job_id="../outside",
        )


def test_language_plan_rejects_han_characters() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    with pytest.raises(DatasetWorkflowError, match="Han characters"):
        build_candidate_from_language_plan(
            {
                "user_messages": ["Merhaba"],
                "intermediate_assistant_response": None,
                "final_response": "你好",
            },
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            registry=ToolRegistry.load(),
        )


def test_language_plan_rejects_other_non_latin_script_leakage() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    with pytest.raises(DatasetWorkflowError, match="unexpected non-Latin"):
        build_candidate_from_language_plan(
            {
                "user_messages": ["Merhaba"],
                "intermediate_assistant_response": None,
                "final_response": "Bu kullanım उचित.",
            },
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            registry=ToolRegistry.load(),
        )


def test_language_plan_allows_micro_unit_symbols() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    candidate = build_candidate_from_language_plan(
        {
            "user_messages": ["PM2.5 değeri nedir?"],
            "intermediate_assistant_response": None,
            "final_response": "Değer 14,2 µg/m³ olarak ölçülmüştür.",
        },
        blueprint=blueprint,
        record_id="tctr_ot_000001",
        registry=ToolRegistry.load(),
    )
    assert candidate["messages"][-1]["content"] == "Değer 14,2 µg/m³ olarak ölçülmüştür."


@pytest.mark.parametrize(
    ("final_response", "message"),
    [
        ("Olay 2026-08-07T02:15:00+03:00 tarihinde gerçekleşti.", "raw ISO timestamp"),
        ("**Sonuç:** gönderi transfer sürecinde.", "markdown formatting"),
    ],
)
def test_language_plan_rejects_machine_style_natural_text(final_response: str, message: str) -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    with pytest.raises(DatasetWorkflowError, match=message):
        build_candidate_from_language_plan(
            {
                "user_messages": ["Gönderi nerede?"],
                "intermediate_assistant_response": None,
                "final_response": final_response,
            },
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            registry=ToolRegistry.load(),
        )


@pytest.mark.parametrize(
    "marker",
    [
        "sentetik",
        "sentetiktir",
        "synthetic",
        "synthetic_pilot_fixture",
        "mock",
        "fixture",
        "fikstür",
        "fully_simulated",
        "simulated",
        "simüle",
        "simülasyon",
    ],
)
def test_language_plan_rejects_internal_operation_markers(marker: str) -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    with pytest.raises(DatasetWorkflowError, match="internal operation markers"):
        build_candidate_from_language_plan(
            {
                "user_messages": ["Merhaba"],
                "intermediate_assistant_response": None,
                "final_response": f"Bu bir {marker} kaydıdır.",
            },
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            registry=ToolRegistry.load(),
        )


def test_language_plan_allows_explicit_internal_marker_topic() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json")
    blueprint["metadata"]["secondary_tags"].append("internal_marker_topic")
    candidate = build_candidate_from_language_plan(
        {
            "user_messages": ["Sentetik veri nedir?"],
            "intermediate_assistant_response": None,
            "final_response": "Sentetik veri, gerçek kayıtların özelliklerini taklit eden yapay veridir.",
        },
        blueprint=blueprint,
        record_id="tctr_ot_000001",
        registry=ToolRegistry.load(),
    )
    assert candidate["metadata"]["secondary_tags"][-1] == "internal_marker_topic"


def test_provider_cannot_self_certify_quality_or_human_review() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "single_tool.json")
    candidate = load(ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json")
    prepared = prepare_generated_candidate(
        candidate,
        blueprint=blueprint,
        record_id="tctr_ot_000001",
        identity=ModelIdentity("fake", "fixture-model", "v1", "dataset_candidate_generator"),
        actor_id="dataset_operator_01",
        generated_at="2026-08-07T00:00:00+00:00",
    )
    assert prepared["metadata"]["review"]["status"] == "needs_revision"
    assert prepared["metadata"]["execution"] == {"type": "local_executable", "status": "not_called"}
    assert prepared["metadata"]["validation"]["tool_call"] == "passed"
    assert prepared["metadata"]["validation"]["execution"] == "not_run"
    assert prepared["metadata"]["validation"]["semantic"] == "not_run"
    assert prepared["metadata"]["validation"]["language"] == "not_run"
    assert prepared["metadata"]["validation"]["duplicate"] == "not_run"
    assert prepared["metadata"]["provenance"]["generator_model"] == "fixture-model"
    assert RuleBasedValidator().validate_record("dataset", prepared).valid
    prepared["metadata"]["review"]["status"] = "accepted"
    report = RuleBasedValidator().validate_record("dataset", prepared)
    assert not report.valid
    assert "REVIEW_ACCEPTED_BEFORE_VALIDATION" in {issue.code for issue in report.issues}


def test_provider_tool_call_must_match_blueprint() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "single_tool.json")
    candidate = load(ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json")
    candidate["messages"][1]["tool_calls"][0]["function"]["arguments"]["left"] = 999
    with pytest.raises(DatasetWorkflowError, match="do not match"):
        prepare_generated_candidate(
            candidate,
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            identity=ModelIdentity("fake", "fixture-model", "v1", "dataset_candidate_generator"),
            actor_id="dataset_operator_01",
            generated_at="2026-08-07T00:00:00+00:00",
        )


def test_provider_tool_result_must_match_blueprint() -> None:
    blueprint = load(ROOT / "tests" / "fixtures" / "blueprints" / "valid" / "single_tool.json")
    candidate = load(ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json")
    candidate["messages"][2]["content"] = json.dumps({"result": 999})
    with pytest.raises(DatasetWorkflowError, match="tool results do not match"):
        prepare_generated_candidate(
            candidate,
            blueprint=blueprint,
            record_id="tctr_ot_000001",
            identity=ModelIdentity("fake", "fixture-model", "v1", "dataset_candidate_generator"),
            actor_id="dataset_operator_01",
            generated_at="2026-08-07T00:00:00+00:00",
        )
