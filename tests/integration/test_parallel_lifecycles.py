from __future__ import annotations

import json
import hashlib
from pathlib import Path

from tool_call_tr.contamination import compare_corpora
from tool_call_tr.deduplication import DeterministicTokenSimilarity
from tool_call_tr.evaluation import BenchmarkEvaluator, run_benchmark
from tool_call_tr.freeze import freeze_benchmark, verify_benchmark_freeze
from tool_call_tr.generation import MockSemanticJudge
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.review import export_accepted
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_dataset_and_benchmark_progress_independently_end_to_end(tmp_path: Path) -> None:
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    validator = RuleBasedValidator(registry=registry)
    dataset = load(ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json")
    benchmark = load(ROOT / "tests" / "fixtures" / "benchmark" / "valid_tool_call.json")

    assert validator.validate_record("dataset", dataset).valid
    assert validator.validate_record("benchmark", benchmark).valid
    contamination = compare_corpora(
        [benchmark],
        [dataset],
        semantic=DeterministicTokenSimilarity(),
    )
    assert contamination.passed

    dataset_output = tmp_path / "data" / "dataset" / "accepted" / "dataset.jsonl"
    assert export_accepted([dataset], dataset_output, validator=validator, kind="dataset") == 1

    gold_output = tmp_path / "data" / "benchmark" / "gold" / "gold.jsonl"
    manifest_output = tmp_path / "data" / "benchmark" / "gold" / "gold.manifest.json"
    manifest = freeze_benchmark(
        [benchmark],
        gold_output,
        manifest_path=manifest_output,
        freeze_id="integration-001",
        frozen_at="2026-08-06T00:00:00+00:00",
        validator=validator,
        contamination_report=contamination,
        dataset_sha256=hashlib.sha256(
            (ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json").read_bytes()
        ).hexdigest(),
    )
    assert manifest["record_ids"] == [benchmark["id"]]
    assert verify_benchmark_freeze(gold_output, manifest_output)["valid"]

    prediction = {
        "benchmark_id": benchmark["id"],
        "prediction": {
            "decision": benchmark["expected"]["decision"],
            "tool_calls": benchmark["expected"]["tool_calls"],
            "response": None,
            "execution_status": "passed",
        },
    }
    frozen_before = gold_output.read_bytes()
    run_log, metrics = run_benchmark(
        [benchmark],
        [prediction],
        evaluator=BenchmarkEvaluator(registry, MockSemanticJudge(1.0)),
        runs_dir=tmp_path / "runs",
        model_name="fixture-model",
        model_version="1",
        run_id="run-001",
    )
    assert metrics["overall_exact_success"] == 1.0
    assert run_log == tmp_path / "runs" / "fixture-model" / "run-001.jsonl"
    assert gold_output.read_bytes() == frozen_before
    assert dataset_output.parent != gold_output.parent
