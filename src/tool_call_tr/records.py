"""Small JSON/JSONL record I/O helpers for explicit CLI workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.validation import ValidationIssue
from tool_call_tr.validation.parsing import parse_path


class RecordIOError(ValueError):
    def __init__(self, message: str, issues: list[ValidationIssue] | None = None) -> None:
        self.issues = issues or []
        super().__init__(message)


def load_records(path: Path) -> list[dict[str, Any]]:
    parsed, issues = parse_path(path)
    if issues:
        raise RecordIOError(f"cannot parse records from {path}", issues)
    records = [record for _, record in parsed]
    if not all(isinstance(record, dict) for record in records):
        raise RecordIOError("every record must be a JSON object")
    return records


def write_records(path: Path, records: Iterable[dict[str, Any]], *, overwrite: bool = False) -> int:
    if path.exists() and not overwrite:
        raise RecordIOError(f"output already exists: {path}")
    values = list(records)
    if path.suffix.lower() == ".jsonl":
        text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in values)
        text += "\n" if values else ""
    else:
        if len(values) != 1:
            raise RecordIOError("JSON output requires exactly one record; use .jsonl for batches")
        text = json.dumps(values[0], ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return len(values)
