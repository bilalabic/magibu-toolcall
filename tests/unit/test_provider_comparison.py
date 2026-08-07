import json
from pathlib import Path

from tool_call_tr.cli import main
from tool_call_tr.generation.providers import ModelIdentity, ProviderResponse
from tool_call_tr.provider_comparison import (
    FLASH_MODEL,
    PRO_MODEL,
    filter_blueprints_by_id,
    recommend_generation_policy,
    run_generation_comparison,
)
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


class FakeGenerator:
    def __init__(self, model: str) -> None:
        self.model = model

    def generate_language_plan(self, blueprint: dict) -> ProviderResponse:
        return ProviderResponse(
            {
                "user_messages": [blueprint["user_goal"]],
                "intermediate_assistant_response": None,
                "final_response": "İstenen sonucu paylaşıyorum.",
            },
            ModelIdentity("deepseek", self.model, f"{self.model}-snapshot", "dataset_language_generator"),
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )


class FakeJudge:
    model = "openai-fixture"

    def judge_record(self, record: dict) -> ProviderResponse:
        scores = {
            "language_naturalness": 5,
            "tool_necessity": 5,
            "tool_selection": 5,
            "argument_grounding": 5,
            "clarification_behavior": 5,
            "result_grounding": 5,
            "turkey_context": 5,
        }
        return ProviderResponse(
            {"verdict": "pass", "scores": scores, "issues": [], "summary": "Uygun."},
            ModelIdentity("openai", self.model, "snapshot", "dataset_quality_judge"),
            usage={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
        )


def test_generation_comparison_builds_paired_valid_candidates() -> None:
    registry = ToolRegistry.load()
    blueprints = [
        json.loads((ROOT / "tests" / "fixtures" / "blueprints" / "valid" / name).read_text(encoding="utf-8"))
        for name in ("no_tool.json", "single_tool.json")
    ]
    result = run_generation_comparison(
        blueprints,
        registry=registry,
        generators={FLASH_MODEL: FakeGenerator(FLASH_MODEL), PRO_MODEL: FakeGenerator(PRO_MODEL)},
        actor_id="dataset_operator_01",
        judge=FakeJudge(),
        generated_at="2026-08-07T00:00:00+00:00",
        max_workers=2,
    )
    assert len(result.candidates[FLASH_MODEL]) == 2
    assert len(result.candidates[PRO_MODEL]) == 2
    assert result.report["models"][FLASH_MODEL]["generation_passed"] == 2
    assert result.report["models"][FLASH_MODEL]["judge_verdicts"] == {"pass": 2}
    assert result.report["decision"]["status"] == "insufficient_sample"


def test_policy_accepts_flash_when_complete_pair_meets_quality_rule() -> None:
    model_report = {
        "generation_failed": 0,
        "judge_failed": 0,
        "mean_overall_score": 4.6,
        "judge_verdicts": {"pass": 30},
    }
    decision = recommend_generation_policy(
        {FLASH_MODEL: model_report, PRO_MODEL: {**model_report, "mean_overall_score": 4.7}},
        sample_size=30,
        judge_enabled=True,
    )
    assert decision["status"] == "accepted"
    assert decision["flash_first"] is True
    assert decision["pro_fallback"] is True


def test_policy_rejects_flash_when_both_models_share_non_passes() -> None:
    report = {
        "generation_failed": 0,
        "judge_failed": 0,
        "mean_overall_score": 4.8,
        "judge_verdicts": {"pass": 29, "fail": 1},
    }
    decision = recommend_generation_policy(
        {FLASH_MODEL: report, PRO_MODEL: report},
        sample_size=30,
        judge_enabled=True,
    )
    assert decision["status"] == "rejected"
    assert "passed 29 of 30" in decision["reasons"][0]


def test_filter_blueprints_by_id_preserves_source_order_and_rejects_unknown() -> None:
    blueprints = [{"id": "bp_a"}, {"id": "bp_b"}, {"id": "bp_c"}]
    assert filter_blueprints_by_id(blueprints, ["bp_c", "bp_a"]) == [
        {"id": "bp_a"},
        {"id": "bp_c"},
    ]
    try:
        filter_blueprints_by_id(blueprints, ["bp_missing"])
    except ValueError as exc:
        assert "bp_missing" in str(exc)
    else:
        raise AssertionError("unknown blueprint ID must fail")


def test_comparison_cli_requires_explicit_live_confirmation(capsys) -> None:
    assert main([
        "provider", "compare-generation", "blueprints.jsonl",
        "--registry", "registry.jsonl",
        "--output-dir", "comparison",
        "--actor-id", "dataset_operator_01",
    ]) == 1
    assert "LIVE_CONFIRMATION_REQUIRED" in capsys.readouterr().out
