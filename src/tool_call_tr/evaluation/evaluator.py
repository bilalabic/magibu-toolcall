"""Benchmark exact-success and five-criterion diagnostic evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from tool_call_tr.generation.providers import SemanticJudge
from tool_call_tr.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class DiagnosticScore:
    behavior_decision: int
    tool_or_order: int
    argument_names_and_types: int
    argument_values: int
    conversation_flow_and_final_behavior: int

    @property
    def total(self) -> int:
        return sum(asdict(self).values())

    def to_dict(self) -> dict[str, int]:
        return {**asdict(self), "total": self.total}


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    benchmark_id: str
    category: str
    secondary_tags: tuple[str, ...]
    exact_success: int
    diagnostic: DiagnosticScore
    schema_valid: bool
    execution_success: bool | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "category": self.category,
            "secondary_tags": list(self.secondary_tags),
            "exact_success": self.exact_success,
            "diagnostic": self.diagnostic.to_dict(),
            "schema_valid": self.schema_valid,
            "execution_success": self.execution_success,
            "errors": list(self.errors),
        }


class BenchmarkEvaluator:
    def __init__(self, registry: ToolRegistry, semantic_judge: SemanticJudge | None = None) -> None:
        self.registry = registry
        self.semantic_judge = semantic_judge

    def evaluate(self, gold: dict[str, Any], prediction: dict[str, Any]) -> EvaluationResult:
        expected = gold["expected"]
        expected_decision = expected["decision"]
        predicted_decision = prediction.get("decision")
        decision_ok = predicted_decision == expected_decision
        expected_calls = expected.get("tool_calls", [])
        predicted_calls = prediction.get("tool_calls", [])
        tags = set(gold["metadata"].get("secondary_tags", []))
        parallel = "parallel_tool" in tags
        tools_ok = decision_ok and self._tool_selection(expected_calls, predicted_calls, parallel)
        names_types_ok = tools_ok and self._argument_structure(expected_calls, predicted_calls, parallel)
        values_ok = tools_ok and self._argument_values(expected_calls, predicted_calls, parallel)
        schema_valid = self._prediction_schema_valid(predicted_calls)
        flow_ok = decision_ok and self._flow(expected, prediction)
        diagnostic = DiagnosticScore(
            int(decision_ok), int(tools_ok), int(names_types_ok), int(values_ok), int(flow_ok)
        )
        errors: list[str] = []
        labels = (
            (decision_ok, "DECISION_INCORRECT"),
            (tools_ok, "TOOL_SELECTION_OR_ORDER_INCORRECT"),
            (names_types_ok, "ARGUMENT_NAMES_OR_TYPES_INCORRECT"),
            (values_ok, "ARGUMENT_VALUES_INCORRECT"),
            (flow_ok, "FLOW_OR_FINAL_BEHAVIOR_INCORRECT"),
            (schema_valid, "PREDICTION_SCHEMA_INVALID"),
        )
        errors.extend(code for passed, code in labels if not passed)
        exact = int(diagnostic.total == 5 and schema_valid)
        execution_status = prediction.get("execution_status")
        execution_success = None if execution_status is None else execution_status == "passed"
        return EvaluationResult(
            gold["id"], gold["metadata"]["main_category"], tuple(gold["metadata"].get("secondary_tags", [])), exact, diagnostic,
            schema_valid, execution_success, tuple(errors),
        )

    def _tool_selection(self, expected: list[dict[str, Any]], predicted: list[dict[str, Any]], parallel: bool) -> bool:
        expected_names = [call["function"]["name"] for call in expected]
        predicted_names = [call.get("function", {}).get("name") for call in predicted]
        if parallel:
            return Counter(expected_names) == Counter(predicted_names)
        return expected_names == predicted_names

    def _argument_structure(self, expected: list[dict[str, Any]], predicted: list[dict[str, Any]], parallel: bool) -> bool:
        def signature(call: dict[str, Any]) -> tuple[Any, ...]:
            function = call.get("function", {})
            arguments = function.get("arguments", {})
            return (
                function.get("name"),
                tuple(sorted(arguments)),
                tuple(sorted((key, _json_type(value)) for key, value in arguments.items())),
            )

        expected_signatures = [signature(call) for call in expected]
        predicted_signatures = [signature(call) for call in predicted]
        shape_equal = Counter(expected_signatures) == Counter(predicted_signatures) if parallel else expected_signatures == predicted_signatures
        if not shape_equal:
            return False
        for call in predicted:
            name = call["function"]["name"]
            try:
                schema = self.registry.by_function_name(name)["function"]["parameters"]
            except KeyError:
                return False
            structural_errors = [
                error for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(call["function"]["arguments"])
                if error.validator in {"required", "type", "additionalProperties"}
            ]
            if structural_errors:
                return False
        return True

    def _argument_values(self, expected: list[dict[str, Any]], predicted: list[dict[str, Any]], parallel: bool) -> bool:
        def canonical(call: dict[str, Any]) -> str:
            import json
            return json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        expected_values = [canonical(call) for call in expected]
        predicted_values = [canonical(call) for call in predicted]
        return Counter(expected_values) == Counter(predicted_values) if parallel else expected_values == predicted_values

    def _prediction_schema_valid(self, calls: list[dict[str, Any]]) -> bool:
        for call in calls:
            try:
                function = call["function"]
                schema = self.registry.by_function_name(function["name"])["function"]["parameters"]
            except (KeyError, TypeError):
                return False
            if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(function.get("arguments"))):
                return False
        return True

    def _flow(self, expected: dict[str, Any], prediction: dict[str, Any]) -> bool:
        decision = expected["decision"]
        calls = prediction.get("tool_calls", [])
        response = prediction.get("response")
        if decision == "tool_call":
            return bool(calls) and response is None and prediction.get("flow_valid", True)
        if calls:
            return False
        if decision == "request_information":
            if set(prediction.get("missing_parameters", [])) != set(expected["missing_parameters"]):
                return False
        if not isinstance(response, str) or not response.strip() or self.semantic_judge is None:
            return False
        judgment = self.semantic_judge.judge(task=decision, candidate=response, reference=expected["response"])
        return bool(judgment.value.get("passed"))


def aggregate_metrics(results: list[EvaluationResult]) -> dict[str, Any]:
    def mean(values: list[int | bool]) -> float | None:
        return sum(values) / len(values) if values else None

    category: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        category[result.category].append(result)
    metrics: dict[str, Any] = {
        "examples": len(results),
        "overall_exact_success": mean([result.exact_success for result in results]),
        "tool_selection_accuracy": mean([result.diagnostic.tool_or_order for result in results]),
        "argument_value_accuracy": mean([result.diagnostic.argument_values for result in results]),
        "schema_validity": mean([result.schema_valid for result in results]),
        "execution_success_rate": mean([result.execution_success for result in results if result.execution_success is not None]),
        "categories": {
            name: {"examples": len(items), "exact_success": mean([item.exact_success for item in items])}
            for name, items in sorted(category.items())
        },
    }
    mapping = {
        "single_tool_success": lambda item: item.category == "single_tool",
        "no_tool_accuracy": lambda item: item.category == "no_tool",
        "clarification_accuracy": lambda item: item.category == "missing_parameter",
        "multi_turn_success": lambda item: item.category == "multi_turn",
        "parallel_tool_success": lambda item: "parallel_tool" in item.secondary_tags,
        "sequential_tool_success": lambda item: "sequential_tool" in item.secondary_tags,
    }
    for name, predicate in mapping.items():
        metrics[name] = mean([item.exact_success for item in results if predicate(item)])
    return metrics


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
