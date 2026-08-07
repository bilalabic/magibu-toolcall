"""Small deterministic guards for provider-authored Turkish prose."""

from __future__ import annotations

import unicodedata


ALLOWED_NON_LATIN_UNIT_LETTERS = {"µ", "μ"}


def contains_unexpected_script(text: str) -> bool:
    """Return true for non-Latin letters except standard micro-unit symbols."""
    return any(
        character not in ALLOWED_NON_LATIN_UNIT_LETTERS
        and
        unicodedata.category(character).startswith("L")
        and "LATIN" not in unicodedata.name(character, "")
        for character in text
    )
