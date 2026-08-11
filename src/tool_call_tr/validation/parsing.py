"""JSON and JSONL parsing with record locations."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from tool_call_tr.record_sources import discover_record_files
from tool_call_tr.validation.diagnostics import ValidationIssue


def parse_path(path: Path) -> tuple[list[tuple[int | None, Any]], list[ValidationIssue]]:
    try:
        files = discover_record_files(path)
    except OSError as exc:
        return [], [ValidationIssue("FILE_READ_ERROR", str(exc))]
    if not files:
        return [], [ValidationIssue("RECORD_SOURCE_EMPTY", "directory contains no JSON/JSONL files")]

    records: list[tuple[int | None, Any]] = []
    issues: list[ValidationIssue] = []
    for file_path in files:
        parsed, file_issues = _parse_file(file_path)
        records.extend(parsed)
        if path.is_dir():
            source = file_path.relative_to(path).as_posix()
            file_issues = [
                replace(issue, message=f"{source}: {issue.message}")
                for issue in file_issues
            ]
        issues.extend(file_issues)
    return records, issues


def _parse_file(path: Path) -> tuple[list[tuple[int | None, Any]], list[ValidationIssue]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [ValidationIssue("FILE_READ_ERROR", str(exc))]
    if path.suffix.lower() != ".jsonl":
        try:
            return [(None, json.loads(text))], []
        except json.JSONDecodeError as exc:
            return [], [ValidationIssue("JSON_PARSE_ERROR", exc.msg, line=exc.lineno)]

    records: list[tuple[int | None, Any]] = []
    issues: list[ValidationIssue] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append((line_number, json.loads(line)))
        except json.JSONDecodeError as exc:
            issues.append(ValidationIssue("JSONL_RECORD_PARSE_ERROR", exc.msg, line=line_number))
    return records, issues
