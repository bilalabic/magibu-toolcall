"""Deterministic corpus and benchmark-run reports."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def corpus_report(
    records: Iterable[dict[str, Any]],
    *,
    kind: str,
    targets: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    values = list(records)
    report = {
        "kind": kind,
        "records": len(values),
        "source_types": _metadata_counts(values, "source_type"),
        "categories": _metadata_counts(values, "main_category"),
        "domains": _metadata_counts(values, "domain"),
        "review_statuses": _nested_counts(values, "review", "status"),
        "execution_statuses": _nested_counts(values, "execution", "status"),
        "fully_validated": sum(
            all(status not in {"failed", "not_run"} for status in record["metadata"]["validation"].values())
            for record in values
        ),
    }
    if targets is not None:
        report["distribution_targets"] = compare_distribution_targets(values, targets)
        report["distribution_targets_met"] = all(
            value["matches"] for value in report["distribution_targets"].values()
        )
    return report


def compare_distribution_targets(
    records: list[dict[str, Any]],
    targets: dict[str, dict[str, int]],
) -> dict[str, Any]:
    supported = {"source_type", "main_category", "domain", "difficulty"}
    unknown = set(targets) - supported
    if unknown:
        raise ValueError("unsupported distribution dimensions: " + ", ".join(sorted(unknown)))
    result: dict[str, Any] = {}
    for dimension, target in targets.items():
        actual = _metadata_counts(records, dimension)
        labels = sorted(set(target) | set(actual))
        delta = {label: actual.get(label, 0) - target.get(label, 0) for label in labels}
        result[dimension] = {
            "target": dict(sorted(target.items())),
            "actual": actual,
            "delta": delta,
            "matches": all(value == 0 for value in delta.values()),
        }
    return result


def benchmark_run_report(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    evaluations = [entry["evaluation"] for entry in entries]

    def mean(values: list[int | bool]) -> float | None:
        return sum(values) / len(values) if values else None

    def selected(predicate) -> list[dict[str, Any]]:
        return [evaluation for evaluation in evaluations if predicate(evaluation)]

    categories = sorted({evaluation["category"] for evaluation in evaluations})
    report: dict[str, Any] = {
        "examples": len(evaluations),
        "overall_exact_success": mean([evaluation["exact_success"] for evaluation in evaluations]),
        "tool_selection_accuracy": mean([evaluation["diagnostic"]["tool_or_order"] for evaluation in evaluations]),
        "argument_value_accuracy": mean([evaluation["diagnostic"]["argument_values"] for evaluation in evaluations]),
        "schema_validity": mean([evaluation["schema_valid"] for evaluation in evaluations]),
        "execution_success_rate": mean([
            evaluation["execution_success"]
            for evaluation in evaluations
            if evaluation["execution_success"] is not None
        ]),
        "categories": {},
    }
    for category in categories:
        items = selected(lambda value, selected_category=category: value["category"] == selected_category)
        report["categories"][category] = {
            "examples": len(items),
            "exact_success": mean([item["exact_success"] for item in items]),
        }
    mapping = {
        "single_tool_success": lambda value: value["category"] == "single_tool",
        "no_tool_accuracy": lambda value: value["category"] == "no_tool",
        "clarification_accuracy": lambda value: value["category"] == "missing_parameter",
        "multi_turn_success": lambda value: value["category"] == "multi_turn",
        "parallel_tool_success": lambda value: "parallel_tool" in value.get("secondary_tags", []),
        "sequential_tool_success": lambda value: "sequential_tool" in value.get("secondary_tags", []),
    }
    for name, predicate in mapping.items():
        items = selected(predicate)
        report[name] = mean([item["exact_success"] for item in items])
    return report


def _metadata_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(record["metadata"][field] for record in records).items()))


def _nested_counts(records: list[dict[str, Any]], parent: str, field: str) -> dict[str, int]:
    return dict(sorted(Counter(record["metadata"][parent][field] for record in records).items()))
