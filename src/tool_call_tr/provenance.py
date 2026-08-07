"""Provenance helpers for transformations and source-level comparison."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


SOURCE_IDENTITY_FIELDS = ("source_dataset", "source_example_id", "upstream_source", "source_split")


@dataclass(frozen=True, slots=True)
class ProvenanceComparison:
    same_source_example: bool
    shared_fields: tuple[str, ...]
    conflicting_fields: tuple[str, ...]


def append_transformation(
    provenance: dict[str, Any],
    *,
    action: str,
    actor_id: str | None = None,
    details: str | None = None,
    timestamp: str | None = None,
    **mode_change: Any,
) -> dict[str, Any]:
    if not action.strip():
        raise ValueError("transformation action cannot be empty")
    updated = copy.deepcopy(provenance)
    event: dict[str, Any] = {
        "action": action,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "details": details,
    }
    for key in ("from_execution_type", "to_execution_type"):
        if key in mode_change:
            event[key] = mode_change[key]
    updated.setdefault("transformation_history", []).append(event)
    return updated


def compare_provenance(left: dict[str, Any], right: dict[str, Any]) -> ProvenanceComparison:
    shared: list[str] = []
    conflicting: list[str] = []
    for field in SOURCE_IDENTITY_FIELDS:
        left_value = left.get(field)
        right_value = right.get(field)
        if left_value is not None and left_value == right_value:
            shared.append(field)
        elif left_value is not None and right_value is not None and left_value != right_value:
            conflicting.append(field)
    same = all(left.get(field) is not None and left.get(field) == right.get(field) for field in ("source_dataset", "source_example_id"))
    return ProvenanceComparison(same, tuple(shared), tuple(conflicting))

