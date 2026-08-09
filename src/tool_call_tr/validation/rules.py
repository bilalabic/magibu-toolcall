"""Layered deterministic validation beyond the JSON Schema contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from tool_call_tr.ids import validate_record_id
from tool_call_tr.registry import RegistryIssue, RegistryValidationError, ToolRegistry
from tool_call_tr.schemas import SchemaStore, json_path
from tool_call_tr.validation.diagnostics import Severity, ValidationIssue, ValidationReport
from tool_call_tr.validation.parsing import parse_path
from tool_call_tr.versioning import VersionError, require_development_version


FORMAT_CHECKER = FormatChecker()


def _child_path(base: str, parts: list[Any]) -> str:
    suffix = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in parts)
    return base + suffix


def _schema_code(error: ValidationError) -> str:
    return {
        "required": "SCHEMA_REQUIRED",
        "enum": "SCHEMA_ENUM",
        "const": "SCHEMA_CONST",
        "pattern": "SCHEMA_PATTERN",
        "type": "SCHEMA_TYPE",
        "additionalProperties": "SCHEMA_ADDITIONAL_PROPERTY",
    }.get(error.validator, "SCHEMA_INVALID")


def _argument_code(error: ValidationError, prefix: str = "ARG") -> str:
    return {
        "required": f"{prefix}_REQUIRED",
        "type": f"{prefix}_TYPE",
        "enum": f"{prefix}_ENUM",
        "format": f"{prefix}_FORMAT",
        "additionalProperties": f"{prefix}_UNSUPPORTED",
    }.get(error.validator, f"{prefix}_SCHEMA_INVALID")


def _without_descriptions(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_descriptions(item) for key, item in value.items() if key != "description"}
    if isinstance(value, list):
        return [_without_descriptions(item) for item in value]
    return value


class RuleBasedValidator:
    def __init__(self, schema_store: SchemaStore | None = None, registry: ToolRegistry | None = None) -> None:
        self.schema_store = schema_store or SchemaStore()
        self.registry = registry or ToolRegistry.load(schema_store=self.schema_store)

    def validate_path(self, kind: str, path: Path) -> ValidationReport:
        if kind == "registry":
            try:
                ToolRegistry.load(path, schema_store=self.schema_store)
            except RegistryValidationError as exc:
                return ValidationReport([_registry_issue(issue) for issue in exc.issues], 0)
            return ValidationReport([], sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()))
        records, parse_issues = parse_path(path)
        report = ValidationReport(parse_issues, len(records))
        for line, record in records:
            report.extend(self.validate_record(kind, record, line=line).issues)
        return report

    def validate_record(self, kind: str, record: Any, *, line: int | None = None) -> ValidationReport:
        record_id = record.get("id") if isinstance(record, dict) else None
        issues = [
            ValidationIssue(_schema_code(error), error.message, json_path(error), record_id=record_id, line=line)
            for error in self.schema_store.errors(kind, record)
        ]
        report = ValidationReport(issues, 1)
        if issues or not isinstance(record, dict):
            return report

        for version_field in ("schema_version", "tool_registry_version"):
            if version_field in record:
                try:
                    require_development_version(record[version_field])
                except VersionError as exc:
                    report.issues.append(ValidationIssue("VERSION_INVALID", str(exc), f"$.{version_field}", record_id=record_id, line=line))

        if kind in {"dataset", "benchmark"}:
            report.extend(self._record_rules(kind, record, line))
        elif kind == "blueprint":
            report.extend(self._blueprint_rules(record, line))
        return report

    def _record_rules(self, kind: str, record: dict[str, Any], line: int | None) -> list[ValidationIssue]:
        record_id = record["id"]
        issues: list[ValidationIssue] = []
        metadata = record["metadata"]
        if not validate_record_id(record_id, kind=kind, source_type=metadata["source_type"]):
            issues.append(ValidationIssue("ID_SOURCE_MISMATCH", "ID prefix must match record kind and source_type", "$.id", record_id=record_id, line=line))

        exposed: dict[str, dict[str, Any]] = {}
        for index, tool_definition in enumerate(record["tools"]):
            name = tool_definition["function"]["name"]
            if name in exposed:
                issues.append(ValidationIssue("DUPLICATE_EXPOSED_FUNCTION", f"function {name} is exposed more than once", f"$.tools[{index}]", record_id=record_id, line=line))
            exposed[name] = tool_definition
            try:
                canonical = self.registry.by_function_name(name)
            except KeyError:
                issues.append(ValidationIssue("FUNCTION_NOT_IN_REGISTRY", f"unknown function: {name}", f"$.tools[{index}].function.name", record_id=record_id, line=line))
                continue
            if _without_descriptions(tool_definition["function"]["parameters"]) != _without_descriptions(canonical["function"]["parameters"]):
                issues.append(ValidationIssue("EXPOSED_TOOL_SCHEMA_MISMATCH", f"parameters for {name} differ from the registry", f"$.tools[{index}].function.parameters", record_id=record_id, line=line))

        calls: dict[str, tuple[str, int, dict[str, Any]]] = {}
        call_groups: list[tuple[int, list[dict[str, Any]]]] = []
        results: dict[str, tuple[str, int]] = {}
        user_turns = 0
        direct_assistant_positions: list[int] = []
        for message_index, message in enumerate(record["messages"]):
            if message["role"] == "user":
                user_turns += 1
            if message["role"] == "assistant" and "tool_calls" not in message:
                direct_assistant_positions.append(message_index)
            if message["role"] == "assistant" and "tool_calls" in message:
                call_groups.append((message_index, message["tool_calls"]))
                for call_index, call in enumerate(message["tool_calls"]):
                    call_id = call["id"]
                    name = call["function"]["name"]
                    path = f"$.messages[{message_index}].tool_calls[{call_index}]"
                    if call_id in calls:
                        issues.append(ValidationIssue("DUPLICATE_TOOL_CALL_ID", f"duplicate tool call ID: {call_id}", f"{path}.id", record_id=record_id, line=line))
                    else:
                        calls[call_id] = (name, message_index, call)
                    if name not in exposed:
                        issues.append(ValidationIssue("FUNCTION_NOT_EXPOSED", f"function {name} was not exposed to the model", f"{path}.function.name", record_id=record_id, line=line))
                    issues.extend(self._validate_arguments(name, call["function"]["arguments"], f"{path}.function.arguments", record_id, line))
            if message["role"] == "tool":
                call_id = message["tool_call_id"]
                path = f"$.messages[{message_index}]"
                if call_id in results:
                    issues.append(ValidationIssue("DUPLICATE_TOOL_RESULT_ID", f"duplicate result for {call_id}", f"{path}.tool_call_id", record_id=record_id, line=line))
                results[call_id] = (message["name"], message_index)
                call = calls.get(call_id)
                if call is None:
                    issues.append(ValidationIssue("UNMATCHED_TOOL_RESULT", f"no preceding call for {call_id}", f"{path}.tool_call_id", record_id=record_id, line=line))
                else:
                    call_name, call_position, _ = call
                    if call_position >= message_index:
                        issues.append(ValidationIssue("TOOL_RESULT_BEFORE_CALL", f"result {call_id} does not follow its call", path, record_id=record_id, line=line))
                    if call_name != message["name"]:
                        issues.append(ValidationIssue("TOOL_RESULT_NAME_MISMATCH", f"result name {message['name']} does not match {call_name}", f"{path}.name", record_id=record_id, line=line))
                    issues.extend(self._validate_result(call_name, message["content"], metadata["execution"]["status"], f"{path}.content", record_id, line))

        if kind == "dataset" and metadata["execution"]["status"] == "passed":
            for call_id in calls.keys() - results.keys():
                issues.append(ValidationIssue("MISSING_TOOL_RESULT", f"no result for {call_id}", "$.messages", record_id=record_id, line=line))

        if kind == "dataset":
            issues.extend(self._category_and_flow_rules(record, call_groups, calls, results, user_turns, direct_assistant_positions, line))
        else:
            issues.extend(self._benchmark_rules(record, exposed, line))
        issues.extend(self._review_rules(record, line))
        if issues and metadata["review"]["status"] == "accepted":
            issues.append(ValidationIssue("ACCEPTED_RECORD_INVALID", f"accepted record has {len(issues)} deterministic error(s)", "$.metadata.review.status", record_id=record_id, line=line))
        return issues

    def _validate_arguments(self, name: str, arguments: dict[str, Any], base: str, record_id: str, line: int | None) -> list[ValidationIssue]:
        try:
            schema = self.registry.by_function_name(name)["function"]["parameters"]
        except KeyError:
            return [ValidationIssue("FUNCTION_NOT_IN_REGISTRY", f"unknown function: {name}", base, record_id=record_id, line=line)]
        return [
            ValidationIssue(_argument_code(error), error.message, _child_path(base, list(error.absolute_path)), record_id=record_id, line=line)
            for error in sorted(Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(arguments), key=lambda error: list(error.absolute_path))
        ]

    def _validate_result(self, name: str, content: str, status: str, base: str, record_id: str, line: int | None) -> list[ValidationIssue]:
        if status in {"empty_result", "invalid_result", "failed", "timeout", "rate_limited"}:
            return []
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            return [ValidationIssue("TOOL_RESULT_JSON_INVALID", exc.msg, base, record_id=record_id, line=line)]
        try:
            schema = self.registry.by_function_name(name)["output_schema"]
        except KeyError:
            return []
        return [
            ValidationIssue(_argument_code(error, "RESULT"), error.message, _child_path(base, list(error.absolute_path)), record_id=record_id, line=line)
            for error in sorted(Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(result), key=lambda error: list(error.absolute_path))
        ]

    def _category_and_flow_rules(
        self,
        record: dict[str, Any],
        call_groups: list[tuple[int, list[dict[str, Any]]]],
        calls: dict[str, tuple[str, int, dict[str, Any]]],
        results: dict[str, tuple[str, int]],
        user_turns: int,
        direct_positions: list[int],
        line: int | None,
    ) -> list[ValidationIssue]:
        record_id = record["id"]
        metadata = record["metadata"]
        category = metadata["main_category"]
        tags = set(metadata["secondary_tags"])
        call_count = sum(len(group) for _, group in call_groups)
        issues: list[ValidationIssue] = []
        if call_count >= 2:
            expected_category = "multi_tool"
        elif user_turns > 1:
            expected_category = "multi_turn"
        elif call_count == 1:
            expected_category = "single_tool"
        else:
            expected_category = category if category in {"no_tool", "missing_parameter"} else "no_tool"
        if category != expected_category:
            issues.append(ValidationIssue("CATEGORY_PRIORITY_MISMATCH", f"observed structure requires main_category={expected_category}", "$.metadata.main_category", record_id=record_id, line=line))
        if "parallel_tool" in tags and "sequential_tool" in tags:
            issues.append(ValidationIssue("TOOL_ORDER_TAG_CONFLICT", "parallel_tool and sequential_tool cannot both be present", "$.metadata.secondary_tags", record_id=record_id, line=line))
        if "parallel_tool" in tags:
            if len(call_groups) != 1 or call_count < 2:
                issues.append(ValidationIssue("PARALLEL_STRUCTURE_INVALID", "parallel calls must be grouped in one assistant message", "$.messages", record_id=record_id, line=line))
        if "sequential_tool" in tags:
            if len(call_groups) < 2 or any(len(group) != 1 for _, group in call_groups):
                issues.append(ValidationIssue("SEQUENTIAL_STRUCTURE_INVALID", "sequential calls must use separate single-call assistant messages", "$.messages", record_id=record_id, line=line))
            else:
                for group_index in range(1, len(call_groups)):
                    current_position = call_groups[group_index][0]
                    previous_ids = {call["id"] for call in call_groups[group_index - 1][1]}
                    if any(call_id not in results or results[call_id][1] >= current_position for call_id in previous_ids):
                        issues.append(ValidationIssue("SEQUENTIAL_ORDER_INVALID", "each prior result must precede the next tool call", "$.messages", record_id=record_id, line=line))
        execution = metadata["execution"]
        if call_count == 0 and (execution["type"] != "not_applicable" or execution["status"] != "not_called"):
            issues.append(ValidationIssue("NO_CALL_EXECUTION_INVALID", "records without calls require not_applicable/not_called execution", "$.metadata.execution", record_id=record_id, line=line))
        if call_count > 0 and execution["type"] == "not_applicable":
            issues.append(ValidationIssue("CALLED_EXECUTION_INVALID", "records with calls require an applicable execution type", "$.metadata.execution", record_id=record_id, line=line))
        if (
            call_count > 0
            and execution["status"] == "not_called"
            and metadata["validation"]["execution"] != "not_run"
        ):
            issues.append(ValidationIssue(
                "UNEXECUTED_RECORD_CLAIMS_VALIDATION",
                "an unexecuted draft must keep validation.execution as not_run",
                "$.metadata.validation.execution",
                record_id=record_id,
                line=line,
            ))
        last_result = max((position for _, position in results.values()), default=-1)
        has_final = any(position > last_result for position in direct_positions) if results else False
        method_present = "final_response_method" in metadata
        if call_count and has_final and not method_present:
            issues.append(ValidationIssue("FINAL_RESPONSE_METHOD_REQUIRED", "a post-tool assistant response requires final_response_method", "$.metadata", record_id=record_id, line=line))
        if (call_count == 0 or not has_final) and method_present:
            issues.append(ValidationIssue("FINAL_RESPONSE_METHOD_NOT_APPLICABLE", "final_response_method is allowed only for a tool-using record with a final response", "$.metadata.final_response_method", record_id=record_id, line=line))
        if category in {"no_tool", "missing_parameter"} and call_count:
            issues.append(ValidationIssue("NO_TOOL_CATEGORY_HAS_CALL", f"{category} must end before any tool call", "$.messages", record_id=record_id, line=line))
        if category in {"no_tool", "missing_parameter"} and (not direct_positions or direct_positions[-1] != len(record["messages"]) - 1):
            issues.append(ValidationIssue("NO_TOOL_FINAL_BEHAVIOR_INVALID", f"{category} must end with an assistant response", "$.messages", record_id=record_id, line=line))
        return issues

    def _benchmark_rules(self, record: dict[str, Any], exposed: dict[str, Any], line: int | None) -> list[ValidationIssue]:
        record_id = record["id"]
        expected = record["expected"]
        category = record["metadata"]["main_category"]
        issues: list[ValidationIssue] = []
        allowed = {
            "single_tool": {"tool_call"},
            "multi_tool": {"tool_call"},
            "no_tool": {"direct_answer", "cannot_answer"},
            "missing_parameter": {"request_information"},
            "multi_turn": {"tool_call", "direct_answer", "request_information", "cannot_answer"},
        }[category]
        if expected["decision"] not in allowed:
            issues.append(ValidationIssue("BENCHMARK_DECISION_INCONSISTENT", f"decision {expected['decision']} is inconsistent with {category}", "$.expected.decision", record_id=record_id, line=line))
        for index, call in enumerate(expected["tool_calls"]):
            name = call["function"]["name"]
            path = f"$.expected.tool_calls[{index}]"
            if name not in exposed:
                issues.append(ValidationIssue("EXPECTED_FUNCTION_NOT_EXPOSED", f"expected function {name} is not exposed", f"{path}.function.name", record_id=record_id, line=line))
            issues.extend(self._validate_arguments(name, call["function"]["arguments"], f"{path}.function.arguments", record_id, line))
        return issues

    def _review_rules(self, record: dict[str, Any], line: int | None) -> list[ValidationIssue]:
        record_id = record["id"]
        metadata = record["metadata"]
        review = metadata["review"]
        issues: list[ValidationIssue] = []
        if review["status"] == "accepted":
            incomplete = [name for name, status in metadata["validation"].items() if status in {"failed", "not_run"}]
            if incomplete:
                issues.append(ValidationIssue("REVIEW_ACCEPTED_BEFORE_VALIDATION", f"validation stages not complete: {', '.join(incomplete)}", "$.metadata.validation", record_id=record_id, line=line))
        return issues

    def _blueprint_rules(self, record: dict[str, Any], line: int | None) -> list[ValidationIssue]:
        record_id = record["id"]
        issues: list[ValidationIssue] = []
        available = set(record["available_tools"])
        for index, name in enumerate(record["available_tools"]):
            if not self.registry.contains_function(name):
                issues.append(ValidationIssue("FUNCTION_NOT_IN_REGISTRY", f"unknown function: {name}", f"$.available_tools[{index}]", record_id=record_id, line=line))
        for index, call in enumerate(record["expected_tool_calls"]):
            name = call["function"]["name"]
            if name not in available:
                issues.append(ValidationIssue("EXPECTED_FUNCTION_NOT_AVAILABLE", f"{name} is not in available_tools", f"$.expected_tool_calls[{index}].function.name", record_id=record_id, line=line))
            issues.extend(self._validate_arguments(name, call["function"]["arguments"], f"$.expected_tool_calls[{index}].function.arguments", record_id, line))
        expected_calls = record["expected_tool_calls"]
        expected_result = record["expected_tool_result"]
        if len(expected_calls) == 1 and expected_result is not None:
            issues.extend(self._validate_output_value(expected_calls[0]["function"]["name"], expected_result, "$.expected_tool_result", record_id, line))
        elif len(expected_calls) > 1 and isinstance(expected_result, list):
            if len(expected_result) != len(expected_calls):
                issues.append(ValidationIssue("BLUEPRINT_RESULT_COUNT_MISMATCH", "one expected result is required per expected call", "$.expected_tool_result", record_id=record_id, line=line))
            for index, (call, result) in enumerate(zip(expected_calls, expected_result, strict=False)):
                issues.extend(self._validate_output_value(call["function"]["name"], result, f"$.expected_tool_result[{index}]", record_id, line))
        category = record["metadata"]["main_category"]
        tags = set(record["metadata"]["secondary_tags"])
        order = record["execution_order"]
        if category == "multi_tool" and ((order == "parallel") != ("parallel_tool" in tags) or (order == "sequential") != ("sequential_tool" in tags)):
            issues.append(ValidationIssue("BLUEPRINT_ORDER_TAG_MISMATCH", "execution_order must match its secondary tag", "$.execution_order", record_id=record_id, line=line))
        if record["expected_behavior"] != "tool_call" and record["metadata"]["intended_execution_type"] != "not_applicable":
            issues.append(ValidationIssue("BLUEPRINT_NO_CALL_EXECUTION_INVALID", "non-tool behavior requires not_applicable execution", "$.metadata.intended_execution_type", record_id=record_id, line=line))
        return issues

    def _validate_output_value(self, name: str, value: Any, base: str, record_id: str, line: int | None) -> list[ValidationIssue]:
        try:
            schema = self.registry.by_function_name(name)["output_schema"]
        except KeyError:
            return []
        return [
            ValidationIssue(_argument_code(error, "RESULT"), error.message, _child_path(base, list(error.absolute_path)), record_id=record_id, line=line)
            for error in sorted(Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(value), key=lambda error: list(error.absolute_path))
        ]


def _registry_issue(issue: RegistryIssue) -> ValidationIssue:
    return ValidationIssue(issue.code, issue.message, issue.path, Severity.ERROR, line=issue.line)
