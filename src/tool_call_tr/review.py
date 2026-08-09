"""Validated accepted-only export for records approved through GitHub PRs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.validation import RuleBasedValidator


class ReviewError(ValueError):
    pass


def export_accepted(
    records: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    validator: RuleBasedValidator,
    kind: str = "dataset",
    overwrite: bool = False,
) -> int:
    if output_path.exists() and not overwrite:
        raise ReviewError(f"output already exists: {output_path}")
    accepted = [copy.deepcopy(record) for record in records if record["metadata"]["review"]["status"] == "accepted"]
    failures = []
    for record in accepted:
        report = validator.validate_record(kind, record)
        if not report.valid:
            failures.append((record.get("id"), report.issues))
    if failures:
        raise ReviewError(f"accepted export blocked by validation failures: {', '.join(str(item[0]) for item in failures)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in accepted)
    output_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return len(accepted)
