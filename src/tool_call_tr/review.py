"""Validated accepted-only export for records approved through GitHub PRs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.text_quality import find_internal_operation_markers
from tool_call_tr.validation import RuleBasedValidator


class ReviewError(ValueError):
    pass


def export_accepted(
    records: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    validator: RuleBasedValidator,
    kind: str = "dataset",
    projection: str = "canonical",
    overwrite: bool = False,
) -> int:
    if projection not in {"canonical", "training"}:
        raise ReviewError(f"unknown export projection: {projection}")
    if projection == "training" and kind != "dataset":
        raise ReviewError("training projection is available only for dataset records")
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
    exported = (
        [project_training_record(record) for record in accepted]
        if projection == "training"
        else accepted
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in exported)
    output_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return len(accepted)


def project_training_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return only fields intended to reach a model-training data loader."""

    projection = {
        "id": record["id"],
        "messages": copy.deepcopy(record["messages"]),
        "tools": copy.deepcopy(record["tools"]),
    }
    tags = record.get("metadata", {}).get("secondary_tags", [])
    if "internal_marker_topic" not in tags:
        leaked_markers = _collect_projection_markers(projection)
        if leaked_markers:
            raise ReviewError(
                "training projection exposes internal operation markers: "
                + ", ".join(leaked_markers)
            )
    return projection


def _collect_projection_markers(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted({
            marker
            for item in value.values()
            for marker in _collect_projection_markers(item)
        })
    if isinstance(value, list):
        return sorted({
            marker
            for item in value
            for marker in _collect_projection_markers(item)
        })
    if isinstance(value, str):
        return list(find_internal_operation_markers(value))
    return []
