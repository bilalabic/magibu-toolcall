"""Grounded Turkish final-response method selection and conflict hooks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import re
from typing import Any, Protocol


NUMBER_RE = re.compile(r"(?<!\w)-?\d+(?:[.,]\d+)?")


class FinalResponseMethod(StrEnum):
    TOOL_RESULT_REGENERATION = "tool_result_regeneration"
    SOURCE_ANSWER_ADAPTATION = "source_answer_adaptation"


@dataclass(frozen=True, slots=True)
class FinalResponseRequest:
    user_request: str
    normalized_tool_result: dict[str, Any] | None
    execution_status: str
    tool_result_validated: bool
    source_answer: str | None = None
    source_answer_verified: bool = False
    conversation_context: tuple[str, ...] = ()
    language: str = "tr"


@dataclass(frozen=True, slots=True)
class FinalResponseOutcome:
    response: str | None
    method: FinalResponseMethod | None
    review_status: str
    conflicts: tuple[str, ...] = ()
    reason: str | None = None


class ToolResultRenderer(Protocol):
    def render(self, request: FinalResponseRequest) -> str:
        ...


class ConflictDetector(Protocol):
    def detect(self, source_answer: str, normalized_tool_result: dict[str, Any]) -> tuple[str, ...]:
        ...


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _scalar_values(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _scalar_values(nested)]
    if value is None:
        return []
    if isinstance(value, bool):
        return [str(value).lower()]
    return [str(value).replace(".", ",")]


class DeterministicConflictDetector:
    def detect(self, source_answer: str, normalized_tool_result: dict[str, Any]) -> tuple[str, ...]:
        allowed_numbers = {value for value in _scalar_values(normalized_tool_result) if NUMBER_RE.fullmatch(value)}
        source_numbers = {value.replace(".", ",") for value in NUMBER_RE.findall(source_answer)}
        unexpected = sorted(source_numbers - allowed_numbers)
        return tuple(f"source answer contains value absent from tool result: {value}" for value in unexpected)


class DeterministicTurkishRenderer:
    """Fixture renderer; production language generation belongs to a provider."""

    def render(self, request: FinalResponseRequest) -> str:
        result = request.normalized_tool_result or {}
        if request.execution_status != "passed":
            error = result.get("error", request.execution_status)
            return f"Araç çağrısı başarısız oldu: {error}."
        if set(result) == {"result"}:
            return f"Sonuç: {str(result['result']).replace('.', ',')}."
        if {"city", "temperature", "unit"} <= set(result):
            unit = "°C" if result["unit"] == "celsius" else "°F"
            return f"{result['city']} için sıcaklık {str(result['temperature']).replace('.', ',')} {unit}."
        return "Araç sonucu: " + json.dumps(result, ensure_ascii=False, sort_keys=True) + "."


class FinalResponseCoordinator:
    def __init__(self, renderer: ToolResultRenderer | None = None, conflict_detector: ConflictDetector | None = None) -> None:
        self.renderer = renderer or DeterministicTurkishRenderer()
        self.conflict_detector = conflict_detector or DeterministicConflictDetector()

    def generate(
        self,
        request: FinalResponseRequest,
        method: FinalResponseMethod | None = None,
    ) -> FinalResponseOutcome:
        if request.language != "tr":
            return FinalResponseOutcome(None, None, "needs_revision", reason="final response language must be Turkish")
        if request.normalized_tool_result is None or not request.tool_result_validated:
            if not (request.source_answer and request.source_answer_verified):
                return FinalResponseOutcome(None, None, "needs_revision", reason="neither tool result nor source answer is verifiable")
            if method != FinalResponseMethod.SOURCE_ANSWER_ADAPTATION:
                return FinalResponseOutcome(None, None, "needs_revision", reason="source-only response requires source_answer_adaptation")
            return FinalResponseOutcome(request.source_answer, method, "needs_revision", reason="tool result is unavailable; human verification required")

        selected = method or FinalResponseMethod.TOOL_RESULT_REGENERATION
        conflicts: tuple[str, ...] = ()
        if request.source_answer:
            conflicts = self.conflict_detector.detect(request.source_answer, request.normalized_tool_result)
        if conflicts:
            selected = FinalResponseMethod.TOOL_RESULT_REGENERATION
        if selected == FinalResponseMethod.SOURCE_ANSWER_ADAPTATION:
            if not request.source_answer or not request.source_answer_verified:
                return FinalResponseOutcome(None, None, "needs_revision", reason="source answer is not verified")
            response = request.source_answer
        else:
            response = self.renderer.render(request)
        if not _numbers_are_grounded(response, request):
            return FinalResponseOutcome(None, selected, "needs_revision", conflicts, "response contains an ungrounded numeric value")
        return FinalResponseOutcome(response, selected, "needs_revision", conflicts)


def _numbers_are_grounded(response: str, request: FinalResponseRequest) -> bool:
    allowed_text = request.user_request + " " + " ".join(request.conversation_context)
    allowed = {value.replace(".", ",") for value in NUMBER_RE.findall(allowed_text)}
    allowed.update(value for value in _scalar_values(request.normalized_tool_result) if NUMBER_RE.fullmatch(value))
    response_numbers = {value.replace(".", ",") for value in NUMBER_RE.findall(response)}
    return response_numbers <= allowed

