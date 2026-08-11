"""Canonical Tool Registry loading and lookup."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from tool_call_tr.config import Settings
from tool_call_tr.record_sources import discover_jsonl_record_files
from tool_call_tr.schemas import SchemaStore, json_path


TOOL_MAJOR_RE = re.compile(r"\.v(?P<major>[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class RegistryIssue:
    code: str
    message: str
    path: str = "$"
    line: int | None = None


class RegistryValidationError(ValueError):
    def __init__(self, issues: list[RegistryIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))


class ToolRegistry:
    def __init__(self, records: list[dict[str, Any]], fixtures_dir: Path | None = None) -> None:
        self.records = tuple(records)
        self.fixtures_dir = fixtures_dir
        self._by_id = {record["tool_id"]: record for record in records}
        self._by_name = {record["function"]["name"]: record for record in records}

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        *,
        schema_store: SchemaStore | None = None,
        fixtures_dir: Path | None = None,
    ) -> "ToolRegistry":
        settings = Settings.from_env()
        path = path or settings.registry_path
        schema_store = schema_store or SchemaStore()
        fixtures_dir = fixtures_dir or (path / "fixtures" if path.is_dir() else path.parent / "fixtures")
        records: list[dict[str, Any]] = []
        locations: list[str] = []
        issues: list[RegistryIssue] = []
        try:
            source_files = discover_jsonl_record_files(path)
        except (OSError, ValueError) as exc:
            raise RegistryValidationError([RegistryIssue("REGISTRY_SOURCE_INVALID", str(exc))]) from exc
        if not source_files:
            raise RegistryValidationError(
                [RegistryIssue("REGISTRY_SOURCE_EMPTY", "directory contains no JSONL files")]
            )

        for file_path in source_files:
            source_name = file_path.name if path.is_dir() else str(file_path)
            parsed_records, parse_issues = _parse_registry_file(file_path, source_name)
            issues.extend(parse_issues)
            for line_number, record in parsed_records:
                location = f"{source_name}:{line_number}" if line_number is not None else source_name
                schema_errors = schema_store.errors("registry", record)
                issues.extend(
                    RegistryIssue(
                        "REGISTRY_SCHEMA_INVALID",
                        f"{location}: {error.message}",
                        json_path(error),
                        line_number,
                    )
                    for error in schema_errors
                )
                if schema_errors:
                    continue
                issues.extend(
                    RegistryIssue(
                        issue.code,
                        f"{location}: {issue.message}",
                        issue.path,
                        issue.line,
                    )
                    for issue in _semantic_record_issues(record, line_number)
                )
                records.append(record)
                locations.append(location)

        seen_ids: dict[str, str] = {}
        seen_names: dict[str, str] = {}
        for record, location in zip(records, locations, strict=True):
            tool_id = record["tool_id"]
            name = record["function"]["name"]
            if tool_id in seen_ids:
                issues.append(
                    RegistryIssue(
                        "DUPLICATE_TOOL_ID",
                        f"{tool_id} first appeared at {seen_ids[tool_id]}; duplicated at {location}",
                        "$.tool_id",
                    )
                )
            else:
                seen_ids[tool_id] = location
            if name in seen_names:
                issues.append(
                    RegistryIssue(
                        "DUPLICATE_FUNCTION_NAME",
                        f"{name} first appeared at {seen_names[name]}; duplicated at {location}",
                        "$.function.name",
                    )
                )
            else:
                seen_names[name] = location
        if issues:
            raise RegistryValidationError(issues)
        return cls(records, fixtures_dir)

    def by_tool_id(self, tool_id: str) -> dict[str, Any]:
        try:
            return self._by_id[tool_id]
        except KeyError as exc:
            raise KeyError(f"unknown tool ID: {tool_id}") from exc

    def by_function_name(self, function_name: str) -> dict[str, Any]:
        try:
            return self._by_name[function_name]
        except KeyError as exc:
            raise KeyError(f"unknown function name: {function_name}") from exc

    def contains_function(self, function_name: str) -> bool:
        return function_name in self._by_name

    def load_fixture(self, fixture_id: str) -> dict[str, Any]:
        if self.fixtures_dir is None:
            raise FileNotFoundError("registry has no fixtures directory")
        path = self.fixtures_dir / f"{fixture_id}.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        tool = self.by_function_name(fixture["function_name"])
        if fixture_id not in tool["execution"]["fixture_ids"]:
            raise ValueError(f"fixture {fixture_id} is not declared by {tool['tool_id']}")
        Draft202012Validator(tool["function"]["parameters"], format_checker=FormatChecker()).validate(fixture["arguments"])
        Draft202012Validator(tool["output_schema"], format_checker=FormatChecker()).validate(fixture["result"])
        return fixture


def _parse_registry_file(
    path: Path,
    source_name: str,
) -> tuple[list[tuple[int | None, Any]], list[RegistryIssue]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [RegistryIssue("REGISTRY_SOURCE_INVALID", f"{source_name}: {exc}")]
    records: list[tuple[int | None, Any]] = []
    issues: list[RegistryIssue] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append((line_number, json.loads(line)))
        except json.JSONDecodeError as exc:
            issues.append(
                RegistryIssue(
                    "REGISTRY_JSON_INVALID",
                    f"{source_name}: {exc.msg}",
                    line=line_number,
                )
            )
    return records, issues


def _semantic_record_issues(record: dict[str, Any], line_number: int | None) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    for field, path in ((record["function"]["parameters"], "$.function.parameters"), (record["output_schema"], "$.output_schema")):
        try:
            Draft202012Validator.check_schema(field)
        except SchemaError as exc:
            issues.append(RegistryIssue("INVALID_JSON_SCHEMA", exc.message, path, line_number))
    if record["execution"]["default_type"] not in record["execution"]["supported_types"]:
        issues.append(RegistryIssue("DEFAULT_EXECUTION_NOT_SUPPORTED", "default_type must occur in supported_types", "$.execution.default_type", line_number))
    supports_real_api = "real_api" in record["execution"]["supported_types"]
    http = record["execution"].get("http")
    if supports_real_api and http is None:
        issues.append(RegistryIssue("REAL_API_HTTP_REQUIRED", "real_api tools require an execution.http contract", "$.execution.http", line_number))
    if not supports_real_api and http is not None:
        issues.append(RegistryIssue("UNUSED_HTTP_CONTRACT", "execution.http is allowed only when real_api is supported", "$.execution.http", line_number))
    if http is not None:
        auth = http["authentication"]
        if auth["type"] == "none" and (auth["env_var"] is not None or auth["header"] is not None or auth["prefix"]):
            issues.append(RegistryIssue("HTTP_AUTH_INVALID", "none authentication cannot declare credential fields", "$.execution.http.authentication", line_number))
        if auth["type"] != "none":
            if not auth["env_var"] or not auth["header"]:
                issues.append(RegistryIssue("HTTP_AUTH_INVALID", "authenticated HTTP contracts require env_var and header", "$.execution.http.authentication", line_number))
            elif auth["env_var"] not in record["access"]["credential_env_vars"]:
                issues.append(RegistryIssue("HTTP_CREDENTIAL_UNDECLARED", "HTTP auth env_var must occur in access.credential_env_vars", "$.execution.http.authentication.env_var", line_number))
        parameter_names = set(record["function"]["parameters"].get("properties", {}))
        mapped_names = set(http["query_map"])
        if mapped_names != parameter_names:
            issues.append(RegistryIssue("HTTP_QUERY_MAP_INCOMPLETE", "HTTP query_map must map every function parameter exactly once", "$.execution.http.query_map", line_number))
        if record["risks"]["side_effects"]:
            issues.append(RegistryIssue("REAL_API_SIDE_EFFECT_FORBIDDEN", "the production HTTP adapter supports read-only tools only", "$.risks.side_effects", line_number))
    tool_major = int(TOOL_MAJOR_RE.search(record["tool_id"]).group("major"))
    version_major = int(record["tool_version"].split(".", 1)[0])
    if tool_major != version_major:
        issues.append(RegistryIssue("TOOL_MAJOR_MISMATCH", "tool ID major must match tool_version major", "$.tool_version", line_number))
    tool_domain = record["tool_id"].split(".", 1)[0]
    if record["domain"] != tool_domain or not record["function"]["name"].startswith(f"{tool_domain}_"):
        issues.append(RegistryIssue("TOOL_DOMAIN_MISMATCH", "tool ID, domain, and function prefix must agree", "$.domain", line_number))
    return issues
