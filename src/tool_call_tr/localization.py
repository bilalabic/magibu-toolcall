"""Apply Turkish localization patches while preserving every machine-facing field."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Iterable

from tool_call_tr.sources import machine_fingerprint


class LocalizationError(ValueError):
    pass


def apply_localization(
    item: dict[str, Any],
    patch: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    example_id = item["source"]["example_id"]
    if patch.get("source_example_id") != example_id:
        raise LocalizationError(f"localization patch ID does not match source item: {example_id}")
    query = patch.get("query")
    if not isinstance(query, str) or not query.strip():
        raise LocalizationError("localized query must be a non-empty string")
    actor_id = patch.get("actor_id")
    provider = patch.get("provider")
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise LocalizationError("localization patch requires actor_id")
    if not isinstance(provider, str) or not provider.strip():
        raise LocalizationError("localization patch requires provider")

    localized = copy.deepcopy(item["content"])
    localized["query"] = query
    tool_descriptions = patch.get("tool_descriptions")
    parameter_descriptions = patch.get("parameter_descriptions")
    if not isinstance(tool_descriptions, dict) or not isinstance(parameter_descriptions, dict):
        raise LocalizationError("localization patch requires tool_descriptions and parameter_descriptions objects")

    expected_tool_names = {tool["name"] for tool in localized["tools"]}
    if set(tool_descriptions) != expected_tool_names or set(parameter_descriptions) != expected_tool_names:
        raise LocalizationError("localization patch tool names must exactly match the source tools")
    for tool in localized["tools"]:
        name = tool["name"]
        description = tool_descriptions[name]
        if not isinstance(description, str) or not description.strip():
            raise LocalizationError(f"localized tool description is empty: {name}")
        tool["description"] = description
        supplied = parameter_descriptions[name]
        properties = tool["parameters"].get("properties", {})
        if not isinstance(supplied, dict) or set(supplied) != set(properties):
            raise LocalizationError(f"localized parameter names must exactly match {name}")
        for parameter_name, parameter in properties.items():
            text = supplied[parameter_name]
            if not isinstance(text, str) or not text.strip():
                raise LocalizationError(f"localized parameter description is empty: {name}.{parameter_name}")
            parameter["description"] = text

    if item["content"]["response"] is not None:
        response = patch.get("response")
        if not isinstance(response, str) or not response.strip():
            raise LocalizationError("a source response requires a localized response")
        localized["response"] = response
    elif patch.get("response") is not None:
        raise LocalizationError("response must stay null when the source has no response")

    original_fingerprint = item["localization"]["machine_fingerprint"]
    if machine_fingerprint(localized) != original_fingerprint:
        raise LocalizationError("localization changed machine-facing fields")
    updated = copy.deepcopy(item)
    updated["localized_content"] = localized
    updated["localization"] = {
        "source_language": item["localization"]["source_language"],
        "target_locale": "tr-TR",
        "status": (
            "localized_needs_source_review"
            if item["localization"]["status"] == "needs_source_review"
            else "localized_needs_review"
        ),
        "actor_id": actor_id,
        "provider": provider,
        "provider_version": patch.get("provider_version"),
        "applied_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "machine_fingerprint": original_fingerprint,
    }
    return updated


def localize_items(
    items: Iterable[dict[str, Any]],
    patches: Iterable[dict[str, Any]],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    patch_map: dict[str, dict[str, Any]] = {}
    for patch in patches:
        patch_id = patch.get("source_example_id")
        if not isinstance(patch_id, str) or not patch_id:
            raise LocalizationError("every localization patch requires source_example_id")
        if patch_id in patch_map:
            raise LocalizationError(f"duplicate localization patch: {patch_id}")
        patch_map[patch_id] = patch
    result = []
    for item in items:
        example_id = item["source"]["example_id"]
        try:
            patch = patch_map.pop(example_id)
        except KeyError as exc:
            raise LocalizationError(f"missing localization patch: {example_id}") from exc
        result.append(apply_localization(item, patch, timestamp=timestamp))
    if patch_map:
        raise LocalizationError("localization patches contain unknown source IDs: " + ", ".join(sorted(patch_map)))
    return result
