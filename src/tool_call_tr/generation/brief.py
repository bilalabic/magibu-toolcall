"""Build the minimal, training-safe context sent to the language generator."""

from __future__ import annotations

from typing import Any

from tool_call_tr.text_quality import find_internal_operation_markers


class GenerationBriefError(ValueError):
    pass


_INTERNAL_RESULT_KEYS = frozenset({
    "data_version",
    "execution_type",
    "fixture_id",
    "intended_execution_type",
    "is_synthetic",
    "provenance",
    "record_id",
    "source",
    "source_id",
    "source_version",
    "synthetic",
})
_OMITTED = object()


def build_generation_brief(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Project a canonical blueprint into the context needed for natural prose only."""

    try:
        metadata = blueprint["metadata"]
        tags = metadata.get("secondary_tags", [])
        allow_internal_markers = "internal_marker_topic" in tags
        brief = {
            "user_goal": blueprint["user_goal"],
            "user_message_count": 2 if metadata["main_category"] == "multi_turn" else 1,
            "clarification_required": "clarification" in tags,
            "tool_use_expected": blueprint["expected_behavior"] == "tool_call",
            "provided_parameters": visible_generation_facts(
                blueprint["provided_parameters"],
                allow_internal_markers=allow_internal_markers,
            ),
            "missing_parameters": list(blueprint["missing_parameters"]),
            "final_response_requirements": blueprint["expected_final_behavior"],
            "avoid": list(blueprint["must_avoid"]),
            "grounding_facts": visible_generation_facts(
                blueprint["expected_tool_result"],
                allow_internal_markers=allow_internal_markers,
            ),
        }
    except (KeyError, TypeError) as exc:
        raise GenerationBriefError("blueprint cannot be projected into a generation brief") from exc

    if not allow_internal_markers:
        leaked_markers = _collect_markers(brief)
        if leaked_markers:
            raise GenerationBriefError(
                "generation brief exposes internal operation markers: " + ", ".join(leaked_markers)
            )
    return brief


def visible_generation_facts(value: Any, *, allow_internal_markers: bool = False) -> Any:
    projected = _visible_facts(value, allow_internal_markers=allow_internal_markers)
    return None if projected is _OMITTED else projected


def _visible_facts(value: Any, *, allow_internal_markers: bool) -> Any:
    if isinstance(value, dict):
        return {
            key: visible
            for key, item in value.items()
            if key not in _INTERNAL_RESULT_KEYS
            for visible in [_visible_facts(item, allow_internal_markers=allow_internal_markers)]
            if visible is not _OMITTED
        }
    if isinstance(value, list):
        return [
            visible
            for item in value
            for visible in [_visible_facts(item, allow_internal_markers=allow_internal_markers)]
            if visible is not _OMITTED
        ]
    if isinstance(value, str) and not allow_internal_markers and find_internal_operation_markers(value):
        return _OMITTED
    return value


def _collect_markers(value: Any) -> list[str]:
    if isinstance(value, dict):
        markers = {
            marker
            for item in value.values()
            for marker in _collect_markers(item)
        }
        return sorted(markers)
    if isinstance(value, list):
        markers = {marker for item in value for marker in _collect_markers(item)}
        return sorted(markers)
    if isinstance(value, str):
        return list(find_internal_operation_markers(value))
    return []
