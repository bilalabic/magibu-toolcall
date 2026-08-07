from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.evaluation import BenchmarkEvaluator, aggregate_metrics, run_log_path, write_run_log
from tool_call_tr.generation.providers import MockSemanticJudge
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def cases() -> dict[str, dict]:
    values = json.loads((ROOT / "tests" / "fixtures" / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    return {case["name"]: case for case in values}


def evaluator() -> BenchmarkEvaluator:
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    return BenchmarkEvaluator(registry, MockSemanticJudge(1.0))


def test_correct_and_incorrect_tool_selection_and_arguments() -> None:
    data = cases()
    correct = evaluator().evaluate(data["correct_tool"]["gold"], data["correct_tool"]["prediction"])
    wrong_tool = evaluator().evaluate(data["wrong_tool"]["gold"], data["wrong_tool"]["prediction"])
    wrong_args = evaluator().evaluate(data["wrong_arguments"]["gold"], data["wrong_arguments"]["prediction"])
    assert correct.exact_success == 1 and correct.diagnostic.total == 5
    assert wrong_tool.exact_success == 0 and wrong_tool.diagnostic.tool_or_order == 0
    assert wrong_args.exact_success == 0 and wrong_args.diagnostic.argument_values == 0
    assert wrong_args.diagnostic.argument_names_and_types == 1


def test_missing_parameter_and_no_tool_semantic_hooks() -> None:
    data = cases()
    assert evaluator().evaluate(data["missing_parameter"]["gold"], data["missing_parameter"]["prediction"]).exact_success == 1
    assert evaluator().evaluate(data["no_tool"]["gold"], data["no_tool"]["prediction"]).exact_success == 1
    no_judge = BenchmarkEvaluator(evaluator().registry)
    assert no_judge.evaluate(data["no_tool"]["gold"], data["no_tool"]["prediction"]).exact_success == 0


def test_parallel_is_order_insensitive_and_sequential_is_order_sensitive() -> None:
    data = cases()
    parallel = evaluator().evaluate(data["parallel_reordered"]["gold"], data["parallel_reordered"]["prediction"])
    sequential = evaluator().evaluate(data["sequential_wrong_order"]["gold"], data["sequential_wrong_order"]["prediction"])
    assert parallel.exact_success == 1
    assert sequential.exact_success == 0
    assert sequential.diagnostic.tool_or_order == 0


def test_metrics_remain_separate_and_category_specific() -> None:
    data = cases()
    results = [evaluator().evaluate(case["gold"], case["prediction"]) for case in data.values()]
    metrics = aggregate_metrics(results)
    assert metrics["examples"] == 7
    assert "overall_exact_success" in metrics
    assert "tool_selection_accuracy" in metrics
    assert "argument_value_accuracy" in metrics
    assert metrics["categories"]["multi_tool"]["examples"] == 2


def test_run_outputs_are_written_below_runs_without_touching_gold(tmp_path: Path) -> None:
    data = cases()["correct_tool"]
    gold_before = json.dumps(data["gold"], sort_keys=True)
    result = evaluator().evaluate(data["gold"], data["prediction"])
    path = write_run_log(tmp_path / "runs", "demo-model", "run-001", [{"benchmark_id": data["gold"]["id"], "prediction": data["prediction"], "evaluation": result.to_dict()}], model_version="fixture")
    assert path == tmp_path / "runs" / "demo-model" / "run-001.jsonl"
    assert json.loads(path.read_text(encoding="utf-8"))["benchmark_id"] == data["gold"]["id"]
    assert json.dumps(data["gold"], sort_keys=True) == gold_before
    with pytest.raises(ValueError):
        run_log_path(tmp_path, "../escape", "run")
