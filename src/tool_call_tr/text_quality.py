"""Small deterministic guards for provider-authored Turkish prose."""

from __future__ import annotations

import re
import unicodedata


ALLOWED_NON_LATIN_UNIT_LETTERS = {"µ", "μ"}
INTERNAL_OPERATION_MARKER_RE = re.compile(
    r"\b(?:sentetik|synthetic|mock|fixture|fikst[uü]r|fully[_ -]simulated|simulated|simulation|simulasyon|simülasyon|simule|simüle)\b",
    re.IGNORECASE,
)


def contains_unexpected_script(text: str) -> bool:
    """Return true for non-Latin letters except standard micro-unit symbols."""
    return any(
        character not in ALLOWED_NON_LATIN_UNIT_LETTERS
        and
        unicodedata.category(character).startswith("L")
        and "LATIN" not in unicodedata.name(character, "")
        for character in text
    )


def find_internal_operation_markers(text: str) -> tuple[str, ...]:
    """Return internal execution/provenance labels leaked into natural prose."""
    return tuple(sorted({match.group(0).casefold() for match in INTERNAL_OPERATION_MARKER_RE.finditer(text)}))
