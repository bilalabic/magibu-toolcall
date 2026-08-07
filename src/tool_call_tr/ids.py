"""Central deterministic identifier generation and collision checks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Collection, Literal


SOURCE_PREFIX = {
    "translated": "tr",
    "original_turkish": "ot",
    "turkey_native": "tn",
}
RECORD_ID_RE = re.compile(r"^(?P<kind>tctr|bench)_(?P<source>tr|ot|tn)_(?P<number>[0-9]{6})$")
CALL_ID_RE = re.compile(r"^call_(?P<number>[0-9]{3,})$")


class IdError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContributorRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1 or self.end > 999_999 or self.start > self.end:
            raise IdError("contributor range must be within 1..999999 and start <= end")

    def contains(self, number: int) -> bool:
        return self.start <= number <= self.end


def generate_record_id(
    kind: Literal["dataset", "benchmark"],
    source_type: str,
    number: int,
    *,
    existing: Collection[str] = (),
    contributor_range: ContributorRange | None = None,
) -> str:
    if source_type not in SOURCE_PREFIX:
        raise IdError(f"unsupported source_type: {source_type}")
    if not 1 <= number <= 999_999:
        raise IdError("record number must be within 1..999999")
    if contributor_range is not None and not contributor_range.contains(number):
        raise IdError(f"number {number} is outside contributor range {contributor_range.start}..{contributor_range.end}")
    root = "tctr" if kind == "dataset" else "bench" if kind == "benchmark" else None
    if root is None:
        raise IdError(f"unsupported record kind: {kind}")
    value = f"{root}_{SOURCE_PREFIX[source_type]}_{number:06d}"
    if value in existing:
        raise IdError(f"ID collision: {value}")
    return value


def generate_call_id(number: int, *, existing: Collection[str] = ()) -> str:
    if number < 1:
        raise IdError("call number must be positive")
    value = f"call_{number:03d}"
    if value in existing:
        raise IdError(f"ID collision: {value}")
    return value


def validate_record_id(value: str, *, kind: str, source_type: str) -> bool:
    match = RECORD_ID_RE.fullmatch(value)
    expected_kind = "tctr" if kind == "dataset" else "bench" if kind == "benchmark" else ""
    return bool(
        match
        and match.group("kind") == expected_kind
        and SOURCE_PREFIX.get(source_type) == match.group("source")
        and int(match.group("number")) > 0
    )


def assert_stable_after_acceptance(original_id: str, proposed_id: str, review_status: str) -> None:
    if review_status == "accepted" and original_id != proposed_id:
        raise IdError("accepted record IDs are immutable")

