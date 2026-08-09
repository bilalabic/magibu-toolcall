"""Provider-independent validation for generated Turkish language plans."""

from __future__ import annotations

import re
from typing import Any

from tool_call_tr.text_quality import contains_unexpected_script, find_internal_operation_markers


class LanguagePlanValidationError(ValueError):
    pass


_RAW_ISO_TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def validate_language_plan(
    language_plan: dict[str, Any],
    *,
    multi_turn: bool,
    requires_clarification: bool = False,
    allow_internal_markers: bool = False,
) -> tuple[list[str], str | None, str]:
    if not isinstance(language_plan, dict) or set(language_plan) != {
        "user_messages", "intermediate_assistant_response", "final_response"
    }:
        raise LanguagePlanValidationError("provider language plan has an invalid shape")
    user_messages = language_plan["user_messages"]
    intermediate_response = language_plan["intermediate_assistant_response"]
    final_response = language_plan["final_response"]
    expected_user_count = 2 if multi_turn else 1
    if (
        not isinstance(user_messages, list)
        or len(user_messages) != expected_user_count
        or any(not isinstance(message, str) or not message.strip() for message in user_messages)
    ):
        raise LanguagePlanValidationError(
            f"provider language plan requires exactly {expected_user_count} non-empty user message(s)"
        )
    if multi_turn:
        if not isinstance(intermediate_response, str) or not intermediate_response.strip():
            raise LanguagePlanValidationError(
                "multi-turn language plan requires an intermediate assistant response"
            )
        if requires_clarification and "?" not in intermediate_response:
            raise LanguagePlanValidationError(
                "multi-turn clarification plan requires an intermediate question"
            )
    elif intermediate_response is not None:
        raise LanguagePlanValidationError(
            "single-turn language plan cannot contain an intermediate assistant response"
        )
    if not isinstance(final_response, str) or not final_response.strip():
        raise LanguagePlanValidationError("provider language plan requires a non-empty final response")
    natural_text = [*user_messages, final_response]
    if intermediate_response is not None:
        natural_text.append(intermediate_response)
    if any(contains_unexpected_script(text) for text in natural_text):
        raise LanguagePlanValidationError(
            "provider language plan contains unexpected non-Latin letters, including Han characters"
        )
    if any("<think" in text.casefold() or "</think" in text.casefold() for text in natural_text):
        raise LanguagePlanValidationError("provider language plan leaked a reasoning tag")
    if any(_RAW_ISO_TIMESTAMP_RE.search(text) for text in natural_text):
        raise LanguagePlanValidationError("provider language plan contains a raw ISO timestamp")
    if any("**" in text or "`" in text for text in natural_text):
        raise LanguagePlanValidationError("provider language plan contains markdown formatting")
    leaked_markers = sorted({marker for text in natural_text for marker in find_internal_operation_markers(text)})
    if leaked_markers and not allow_internal_markers:
        raise LanguagePlanValidationError(
            "provider language plan exposes internal operation markers: " + ", ".join(leaked_markers)
        )
    return user_messages, intermediate_response, final_response
