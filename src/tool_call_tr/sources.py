"""Source-format adapters for provenance-safe xLAM and When2Call imports."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Protocol


XLAM_DATASET = "Salesforce/xlam-function-calling-60k"
WHEN2CALL_DATASET = "nvidia/When2Call"
SOURCE_LICENSE = "cc-by-4.0"


class SourceIngestionError(ValueError):
    pass


class SourceAdapter(Protocol):
    def convert(self, row: dict[str, Any], *, row_number: int, source_file: str, split: str) -> dict[str, Any]:
        ...


def iter_source_rows(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    """Read a JSON object/array or stream JSONL rows with stable row numbers."""

    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SourceIngestionError(f"invalid JSONL at line {line_number}: {exc.msg}") from exc
                if not isinstance(value, dict):
                    raise SourceIngestionError(f"source row {line_number} must be a JSON object")
                yield line_number, value
        return

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceIngestionError(f"cannot read source JSON: {path}") from exc
    rows = value if isinstance(value, list) else [value]
    for row_number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise SourceIngestionError(f"source row {row_number} must be a JSON object")
        yield row_number, row


def import_source(
    path: Path,
    *,
    source: str,
    split: str,
    source_terms_accepted: bool = False,
) -> list[dict[str, Any]]:
    if not split.strip():
        raise SourceIngestionError("source split cannot be empty")
    adapter = get_source_adapter(source, source_terms_accepted=source_terms_accepted)
    return [
        adapter.convert(row, row_number=row_number, source_file=path.name, split=split)
        for row_number, row in iter_source_rows(path)
    ]


def get_source_adapter(source: str, *, source_terms_accepted: bool = False) -> SourceAdapter:
    if source == "xlam":
        if not source_terms_accepted:
            raise SourceIngestionError("xLAM import requires explicit source-terms acceptance")
        return XlamAdapter(terms_accepted=True)
    if source == "when2call":
        return When2CallAdapter()
    raise SourceIngestionError(f"unsupported source: {source}")


class XlamAdapter:
    def __init__(self, *, terms_accepted: bool) -> None:
        if not terms_accepted:
            raise SourceIngestionError("xLAM repository terms must be accepted by the operator")
        self.terms_accepted = terms_accepted

    def convert(self, row: dict[str, Any], *, row_number: int, source_file: str, split: str) -> dict[str, Any]:
        query = _required_string(row, "query", row_number)
        tools = _decode_json_field(row.get("tools"), "tools", row_number)
        answers = _decode_json_field(row.get("answers"), "answers", row_number)
        if not isinstance(tools, list) or not isinstance(answers, list):
            raise SourceIngestionError(f"xLAM row {row_number} requires tools and answers arrays")
        content = {
            "query": query,
            "tools": [_normalize_tool(item, row_number) for item in tools],
            "decision": "tool_call",
            "missing_parameters": [],
            "tool_calls": [_normalize_tool_call(item, row_number) for item in answers],
            "response": None,
        }
        example_id = str(row.get("id", f"row-{row_number:06d}"))
        return _work_item(
            dataset=XLAM_DATASET,
            source_format="xlam_function_calling_60k",
            example_id=example_id,
            split=split,
            source_file=source_file,
            row_number=row_number,
            row=row,
            terms_accepted=True,
            content=content,
            status="pending",
        )


class When2CallAdapter:
    def convert(self, row: dict[str, Any], *, row_number: int, source_file: str, split: str) -> dict[str, Any]:
        if "correct_answer" in row:
            source_format = "when2call_test"
            content, status = self._test_content(row, row_number)
        elif "chosen_response" in row and "rejected_response" in row:
            source_format = "when2call_train_pref"
            content, status = self._training_content(row, row_number, "chosen_response")
        elif "messages" in row:
            source_format = "when2call_train_sft"
            content, status = self._training_content(row, row_number, None)
        else:
            raise SourceIngestionError(f"When2Call row {row_number} has an unknown official format")
        example_id = str(row.get("uuid") or row.get("source_id") or f"row-{row_number:06d}")
        return _work_item(
            dataset=WHEN2CALL_DATASET,
            source_format=source_format,
            example_id=example_id,
            split=split,
            source_file=source_file,
            row_number=row_number,
            row=row,
            terms_accepted=True,
            content=content,
            status=status,
        )

    def _test_content(self, row: dict[str, Any], row_number: int) -> tuple[dict[str, Any], str]:
        mapping = {
            "direct": "direct_answer",
            "tool_call": "tool_call",
            "request_for_info": "request_information",
            "cannot_answer": "cannot_answer",
        }
        label = row.get("correct_answer")
        try:
            decision = mapping[label]
        except KeyError as exc:
            raise SourceIngestionError(f"When2Call row {row_number} has unsupported correct_answer: {label}") from exc
        tools_value = _decode_json_field(row.get("tools", []), "tools", row_number)
        if not isinstance(tools_value, list):
            raise SourceIngestionError(f"When2Call row {row_number} tools must be an array")
        tools = [_normalize_tool(item, row_number) for item in tools_value]
        answers = row.get("answers")
        if not isinstance(answers, dict):
            raise SourceIngestionError(f"When2Call row {row_number} answers must be an object")
        tool_calls: list[dict[str, Any]] = []
        response: str | None = None
        if decision == "tool_call":
            raw_call = _decode_json_field(answers.get("tool_call"), "answers.tool_call", row_number)
            calls = raw_call if isinstance(raw_call, list) else [raw_call]
            tool_calls = [_normalize_tool_call(item, row_number) for item in calls]
        else:
            response = answers.get(str(label))
            if not isinstance(response, str) or not response.strip():
                raise SourceIngestionError(f"When2Call row {row_number} lacks the selected response")
        held_out = row.get("held_out_param")
        missing = [held_out] if decision == "request_information" and isinstance(held_out, str) and held_out else []
        if decision == "request_information" and not missing:
            return ({
                "query": _required_string(row, "question", row_number), "tools": tools,
                "decision": decision, "missing_parameters": [], "tool_calls": [], "response": response,
            }, "needs_source_review")
        return ({
            "query": _required_string(row, "question", row_number),
            "tools": tools,
            "decision": decision,
            "missing_parameters": missing,
            "tool_calls": tool_calls,
            "response": response,
        }, "pending")

    def _training_content(self, row: dict[str, Any], row_number: int, selected_response: str | None) -> tuple[dict[str, Any], str]:
        messages = row.get("messages")
        if not isinstance(messages, list):
            raise SourceIngestionError(f"When2Call row {row_number} messages must be an array")
        user_messages = [item.get("content") for item in messages if isinstance(item, dict) and item.get("role") == "user"]
        if not user_messages or not isinstance(user_messages[-1], str):
            raise SourceIngestionError(f"When2Call row {row_number} lacks a user message")
        tools_value = _decode_json_field(row.get("tools", []), "tools", row_number)
        if not isinstance(tools_value, list):
            raise SourceIngestionError(f"When2Call row {row_number} tools must be an array")
        response_value: Any = row.get(selected_response) if selected_response else next(
            (item for item in reversed(messages) if isinstance(item, dict) and item.get("role") == "assistant"),
            None,
        )
        response = response_value.get("content") if isinstance(response_value, dict) else None
        return ({
            "query": user_messages[-1],
            "tools": [_normalize_tool(item, row_number) for item in tools_value],
            "decision": None,
            "missing_parameters": [],
            "tool_calls": [],
            "response": response if isinstance(response, str) and response.strip() else None,
        }, "needs_source_review")


def _work_item(
    *, dataset: str, source_format: str, example_id: str, split: str, source_file: str,
    row_number: int, row: dict[str, Any], terms_accepted: bool, content: dict[str, Any], status: str,
) -> dict[str, Any]:
    fingerprint = machine_fingerprint(content)
    return {
        "ingestion_version": "0.1.0",
        "source": {
            "dataset": dataset,
            "format": source_format,
            "example_id": example_id,
            "split": split,
            "license": SOURCE_LICENSE,
            "license_chain": [SOURCE_LICENSE],
            "source_file": source_file,
            "row_number": row_number,
            "raw_sha256": _canonical_hash(row),
            "terms_accepted": terms_accepted,
        },
        "content": content,
        "localized_content": None,
        "localization": {
            "source_language": "en",
            "target_locale": "tr-TR",
            "status": status,
            "actor_id": None,
            "provider": None,
            "provider_version": None,
            "applied_at": None,
            "machine_fingerprint": fingerprint,
        },
    }


def machine_fingerprint(content: dict[str, Any]) -> str:
    machine = copy.deepcopy(content)
    machine.pop("query", None)
    machine.pop("response", None)
    for tool in machine.get("tools", []):
        tool.pop("description", None)
        _remove_descriptions(tool.get("parameters"))
    return _canonical_hash(machine)


def _remove_descriptions(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("description", None)
        for child in value.values():
            _remove_descriptions(child)
    elif isinstance(value, list):
        for child in value:
            _remove_descriptions(child)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decode_json_field(value: Any, name: str, row_number: int) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise SourceIngestionError(f"source row {row_number} field {name} contains invalid JSON") from exc
    return value


def _required_string(row: dict[str, Any], name: str, row_number: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise SourceIngestionError(f"source row {row_number} field {name} must be a non-empty string")
    return value


def _normalize_tool(value: Any, row_number: int) -> dict[str, Any]:
    value = _decode_json_field(value, "tool", row_number)
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        raise SourceIngestionError(f"source row {row_number} contains an invalid tool")
    parameters = value.get("parameters", {})
    parameters = _decode_json_field(parameters, "tool.parameters", row_number)
    if not isinstance(parameters, dict):
        raise SourceIngestionError(f"source row {row_number} tool parameters must be an object")
    return {
        "name": value["name"],
        "description": value.get("description") if isinstance(value.get("description"), str) else "",
        "parameters": _normalize_parameter_schema(parameters),
    }


def _normalize_parameter_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    if "properties" in parameters:
        schema = copy.deepcopy(parameters)
        schema["type"] = "object" if schema.get("type") in {None, "dict"} else _json_type(schema["type"])
        schema["properties"] = {
            key: _normalize_property(value) for key, value in schema.get("properties", {}).items()
        }
        if "required" not in schema:
            schema["required"] = []
        schema.setdefault("additionalProperties", False)
        return schema
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, definition in parameters.items():
        if not isinstance(definition, dict):
            definition = {"type": "string", "description": str(definition)}
        item = copy.deepcopy(definition)
        if item.pop("required", False):
            required.append(name)
        properties[name] = _normalize_property(item)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _normalize_property(value: Any) -> dict[str, Any]:
    item = copy.deepcopy(value) if isinstance(value, dict) else {"type": "string"}
    if "type" in item:
        item["type"] = _json_type(item["type"])
    return item


def _json_type(value: Any) -> Any:
    mapping = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object"}
    if isinstance(value, list):
        return [mapping.get(item, item) for item in value]
    return mapping.get(value, value)


def _normalize_tool_call(value: Any, row_number: int) -> dict[str, Any]:
    value = _decode_json_field(value, "tool_call", row_number)
    if not isinstance(value, dict):
        raise SourceIngestionError(f"source row {row_number} contains an invalid tool call")
    name = value.get("name")
    arguments = _decode_json_field(value.get("arguments", {}), "tool_call.arguments", row_number)
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise SourceIngestionError(f"source row {row_number} tool call requires name and object arguments")
    return {"name": name, "arguments": arguments}
