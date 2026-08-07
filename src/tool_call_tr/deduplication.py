"""Deterministic duplicate signals and a semantic-similarity seam."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping, Protocol, Sequence

from tool_call_tr.provenance import compare_provenance


TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def exact_query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def normalize_query(query: str, entity_values: Mapping[str, Sequence[str]] | None = None) -> str:
    value = unicodedata.normalize("NFKC", query).casefold().replace("i\u0307", "i")
    if entity_values:
        replacements: list[tuple[str, str]] = []
        for entity_type, values in entity_values.items():
            replacements.extend((unicodedata.normalize("NFKC", item).casefold().replace("i\u0307", "i"), f" <{entity_type}> ") for item in values)
        for source, target in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
            value = value.replace(source, target)
    return " ".join(TOKEN_RE.findall(value))


def normalized_query_hash(query: str, entity_values: Mapping[str, Sequence[str]] | None = None) -> str:
    return exact_query_hash(normalize_query(query, entity_values))


def _canonical_schema(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        ignored = {"description", "title", "$comment", "examples"}
        return {key: _canonical_schema(item, key) for key, item in sorted(value.items()) if key not in ignored}
    if isinstance(value, list):
        items = [_canonical_schema(item, parent_key) for item in value]
        if parent_key in {"required", "enum", "type"}:
            return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        return items
    return value


def tool_schema_fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(_canonical_schema(schema), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def combined_query_schema_hash(query: str, schemas: Sequence[dict[str, Any]]) -> str:
    schema_hashes = sorted(tool_schema_fingerprint(schema) for schema in schemas)
    value = normalized_query_hash(query) + ":" + ":".join(schema_hashes)
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class SemanticSimilarity(Protocol):
    def score(self, left: str, right: str) -> float:
        ...


class DeterministicTokenSimilarity:
    """A deterministic test double, not the production semantic model."""

    def score(self, left: str, right: str) -> float:
        left_tokens = set(normalize_query(left).split())
        right_tokens = set(normalize_query(right).split())
        if not left_tokens and not right_tokens:
            return 1.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    left_id: str
    right_id: str
    exact_query: bool
    normalized_query: bool
    entity_shape: bool
    tool_schema_match: bool
    combined_match: bool
    source_example_match: bool
    semantic_similarity: float | None
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _query(record: dict[str, Any]) -> str:
    return "\n".join(message["content"] for message in record.get("messages", []) if message.get("role") == "user")


def _schemas(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [tool["function"]["parameters"] for tool in record.get("tools", [])]


def compare_records(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    semantic: SemanticSimilarity | None = None,
    semantic_threshold: float = 0.9,
    entity_values: Mapping[str, Sequence[str]] | None = None,
) -> DuplicateReport:
    left_query, right_query = _query(left), _query(right)
    exact = exact_query_hash(left_query) == exact_query_hash(right_query)
    normalized = normalized_query_hash(left_query) == normalized_query_hash(right_query)
    shape = bool(entity_values) and normalized_query_hash(left_query, entity_values) == normalized_query_hash(right_query, entity_values)
    left_schemas, right_schemas = _schemas(left), _schemas(right)
    schema_match = sorted(map(tool_schema_fingerprint, left_schemas)) == sorted(map(tool_schema_fingerprint, right_schemas))
    combined = combined_query_schema_hash(left_query, left_schemas) == combined_query_schema_hash(right_query, right_schemas)
    provenance = compare_provenance(left["metadata"]["provenance"], right["metadata"]["provenance"])
    semantic_score = semantic.score(left_query, right_query) if semantic else None
    if exact or provenance.same_source_example or combined:
        decision = "duplicate"
    elif shape or (semantic_score is not None and semantic_score >= semantic_threshold):
        decision = "possible_duplicate"
    elif semantic_score is None:
        decision = "needs_semantic_review"
    else:
        decision = "distinct"
    return DuplicateReport(
        left["id"], right["id"], exact, normalized, shape, schema_match, combined,
        provenance.same_source_example, semantic_score, decision,
    )
