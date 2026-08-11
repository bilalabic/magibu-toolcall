"""Scenario blueprint storage and narrow candidate-conversion hooks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Protocol

from tool_call_tr.record_sources import discover_record_files
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator, ValidationIssue
from tool_call_tr.validation.parsing import parse_path


class BlueprintError(ValueError):
    def __init__(self, message: str, issues: list[ValidationIssue] | None = None) -> None:
        self.issues = issues or []
        super().__init__(message)


class BlueprintStore:
    def __init__(self, records: dict[str, dict[str, Any]]) -> None:
        self._records = records

    @classmethod
    def load_directory(cls, path: Path, validator: RuleBasedValidator) -> "BlueprintStore":
        records: dict[str, dict[str, Any]] = {}
        try:
            source_files = discover_record_files(path)
        except OSError as exc:
            raise BlueprintError(f"invalid blueprint source: {exc}") from exc
        if not source_files:
            raise BlueprintError("blueprint directory contains no JSON/JSONL files")

        locations: dict[str, str] = {}
        for file_path in source_files:
            parsed_records, parse_issues = parse_path(file_path)
            if parse_issues:
                raise BlueprintError(f"invalid blueprint: {file_path.name}", parse_issues)
            for line_number, record in parsed_records:
                report = validator.validate_record("blueprint", record)
                if not report.valid:
                    raise BlueprintError(f"invalid blueprint: {file_path.name}", report.issues)
                blueprint_id = record["id"]
                location = f"{file_path.name}:{line_number}" if line_number is not None else file_path.name
                if blueprint_id in records:
                    raise BlueprintError(
                        f"duplicate blueprint ID: {blueprint_id} "
                        f"({locations[blueprint_id]} and {location})"
                    )
                records[blueprint_id] = record
                locations[blueprint_id] = location
        return cls(records)

    def get(self, blueprint_id: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self._records[blueprint_id])
        except KeyError as exc:
            raise KeyError(f"unknown blueprint ID: {blueprint_id}") from exc

    def by_category(self, category: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(record) for record in self._records.values() if record["metadata"]["main_category"] == category]


def infer_main_category(*, user_turns: int, tool_call_count: int, decision: str) -> str:
    """Apply the specification's priority order exactly."""

    if tool_call_count >= 2:
        return "multi_tool"
    if user_turns > 1:
        return "multi_turn"
    if decision == "request_information":
        return "missing_parameter"
    if decision in {"direct_answer", "cannot_answer"}:
        return "no_tool"
    if tool_call_count == 1:
        return "single_tool"
    raise BlueprintError("the supplied structure does not map to a main category")


class CandidateConverter(Protocol):
    def convert(self, blueprint: dict[str, Any], *, record_id: str, user_message: str) -> dict[str, Any]:
        ...


class BenchmarkCandidateConverter:
    """Build a review-required benchmark draft; it never accepts or executes it."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def convert(self, blueprint: dict[str, Any], *, record_id: str, user_message: str) -> dict[str, Any]:
        decision = blueprint["expected_behavior"]
        tool_expected = decision == "tool_call"
        tools = []
        for name in blueprint["available_tools"]:
            canonical = self.registry.by_function_name(name)
            tools.append({"type": "function", "function": copy.deepcopy(canonical["function"])})
        validation = {
            "json": "passed",
            "schema": "passed",
            "tool_call": "not_run" if tool_expected else "not_applicable",
            "execution": "not_run" if tool_expected else "not_applicable",
            "semantic": "not_run",
            "turn_level": "not_run" if blueprint["metadata"]["main_category"] == "multi_turn" else "not_applicable",
            "language": "not_run",
            "duplicate": "not_run",
        }
        execution = (
            {"type": blueprint["metadata"]["intended_execution_type"], "status": "not_called"}
            if tool_expected
            else {"type": "not_applicable", "status": "not_called"}
        )
        metadata = {
            "main_category": blueprint["metadata"]["main_category"],
            "secondary_tags": copy.deepcopy(blueprint["metadata"]["secondary_tags"]),
            "source_type": blueprint["metadata"]["source_type"],
            "domain": blueprint["metadata"]["domain"],
            "difficulty": blueprint["metadata"]["difficulty"],
            "provenance": copy.deepcopy(blueprint["metadata"]["provenance"]),
            "execution": execution,
            "validation": validation,
            "review": {
                "status": "needs_revision",
                "notes": f"Generated deterministically from blueprint {blueprint['id']}; GitHub PR review is required.",
            },
        }
        return {
            "schema_version": blueprint["schema_version"],
            "tool_registry_version": blueprint["tool_registry_version"],
            "id": record_id,
            "metadata": metadata,
            "tools": tools,
            "messages": [{"role": "user", "content": user_message}],
            "expected": {
                "decision": decision,
                "missing_parameters": copy.deepcopy(blueprint["missing_parameters"]),
                "tool_calls": copy.deepcopy(blueprint["expected_tool_calls"]),
                "response": None if tool_expected else blueprint["expected_final_behavior"],
            },
        }
