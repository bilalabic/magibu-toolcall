"""Run isolated predictions against benchmark gold and persist run outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.evaluation.evaluator import BenchmarkEvaluator, aggregate_metrics
from tool_call_tr.evaluation.run_logs import write_run_log


class BenchmarkRunError(ValueError):
    pass


def run_benchmark(
    gold_records: Iterable[dict[str, Any]],
    prediction_records: Iterable[dict[str, Any]],
    *,
    evaluator: BenchmarkEvaluator,
    runs_dir: Path,
    model_name: str,
    run_id: str,
    model_version: str | None = None,
    overwrite: bool = False,
) -> tuple[Path, dict[str, Any]]:
    gold = list(gold_records)
    if not gold:
        raise BenchmarkRunError("benchmark gold cannot be empty")
    gold_id_values = [record.get("id") for record in gold]
    duplicate_gold_ids = sorted({record_id for record_id in gold_id_values if gold_id_values.count(record_id) > 1})
    if duplicate_gold_ids:
        raise BenchmarkRunError("benchmark gold IDs must be unique: " + ", ".join(map(str, duplicate_gold_ids)))
    predictions = _prediction_index(prediction_records)
    gold_ids = {record["id"] for record in gold}
    unexpected = sorted(set(predictions) - gold_ids)
    if unexpected:
        raise BenchmarkRunError("predictions contain unknown benchmark IDs: " + ", ".join(unexpected))

    results = []
    outputs = []
    for record in gold:
        benchmark_id = record["id"]
        missing = benchmark_id not in predictions
        prediction = predictions.get(benchmark_id, {})
        result = evaluator.evaluate(record, prediction)
        results.append(result)
        outputs.append(
            {
                "benchmark_id": benchmark_id,
                "prediction": prediction,
                "missing_prediction": missing,
                "evaluation": result.to_dict(),
            }
        )
    path = write_run_log(
        runs_dir,
        model_name,
        run_id,
        outputs,
        model_version=model_version,
        overwrite=overwrite,
    )
    return path, aggregate_metrics(results)


def _prediction_index(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        try:
            benchmark_id = record["benchmark_id"]
            prediction = record["prediction"]
        except (KeyError, TypeError) as exc:
            raise BenchmarkRunError("prediction records require benchmark_id and prediction") from exc
        if not isinstance(benchmark_id, str) or not isinstance(prediction, dict):
            raise BenchmarkRunError("benchmark_id must be a string and prediction must be an object")
        if benchmark_id in result:
            raise BenchmarkRunError(f"duplicate prediction for benchmark ID: {benchmark_id}")
        result[benchmark_id] = prediction
    return result
