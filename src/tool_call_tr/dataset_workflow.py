"""Quality-first helpers for the normal Turkish dataset generation workflow."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from tool_call_tr.generation.providers import ModelIdentity
from tool_call_tr.ids import RECORD_ID_RE, SOURCE_PREFIX
from tool_call_tr.validation import RuleBasedValidator
from tool_call_tr.validation.parsing import parse_path


ACTIVE_DATASET_SOURCE_TYPES = {"original_turkish", "turkey_native"}
TARGET_DIMENSIONS = ("main_category", "source_type", "domain", "difficulty")
JOB_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class DatasetWorkflowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BlueprintPlan:
    total_items: int
    source_type: str
    target_distributions: dict[str, dict[str, int]]


@dataclass(frozen=True, slots=True)
class DatasetJobPaths:
    job_dir: Path
    manifest: Path
    checkpoint: Path
    errors: Path
    output: Path


def inspect_blueprints(path: Path, *, validator: RuleBasedValidator | None = None) -> BlueprintPlan:
    """Validate every blueprint before any provider call and derive its frozen distribution plan."""

    parsed, parse_issues = parse_path(path)
    if parse_issues:
        detail = "; ".join(f"{issue.code}: {issue.message}" for issue in parse_issues)
        raise DatasetWorkflowError(f"blueprint input cannot be parsed: {detail}")
    if not parsed:
        raise DatasetWorkflowError("blueprint input cannot be empty")

    validator = validator or RuleBasedValidator()
    blueprint_ids: set[str] = set()
    distributions: dict[str, dict[str, int]] = {dimension: {} for dimension in TARGET_DIMENSIONS}
    source_types: set[str] = set()
    failures: list[str] = []
    for line, blueprint in parsed:
        report = validator.validate_record("blueprint", blueprint, line=line)
        if not report.valid:
            failures.append(report.human())
            continue
        blueprint_id = blueprint["id"]
        if blueprint_id in blueprint_ids:
            failures.append(f"ERROR BLUEPRINT_ID_DUPLICATE: duplicate blueprint ID: {blueprint_id}")
            continue
        blueprint_ids.add(blueprint_id)
        metadata = blueprint["metadata"]
        source_types.add(metadata["source_type"])
        for dimension in TARGET_DIMENSIONS:
            value = metadata[dimension]
            counts = distributions[dimension]
            counts[value] = counts.get(value, 0) + 1
    if failures:
        raise DatasetWorkflowError("\n".join(failures))
    if len(source_types) != 1:
        raise DatasetWorkflowError("one generation job must contain exactly one source_type")
    source_type = next(iter(source_types))
    if source_type not in ACTIVE_DATASET_SOURCE_TYPES:
        raise DatasetWorkflowError(
            "normal dataset generation supports original_turkish or turkey_native; translation is paused"
        )
    return BlueprintPlan(len(parsed), source_type, distributions)


def default_job_id(input_path: Path, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    stem = re.sub(r"[^a-z0-9_-]+", "-", input_path.stem.lower()).strip("-_") or "blueprints"
    stem = stem[:35].rstrip("-_") or "blueprints"
    return f"dataset-{stem}-{timestamp}"


def default_job_paths(
    *,
    project_root: Path,
    runs_dir: Path,
    job_id: str,
    output_path: Path | None = None,
) -> DatasetJobPaths:
    if not JOB_ID_RE.fullmatch(job_id):
        raise DatasetWorkflowError("job_id must match ^[a-z][a-z0-9_-]{2,63}$")
    job_dir = (runs_dir / "dataset" / job_id).resolve()
    output = (
        output_path.resolve()
        if output_path is not None
        else (project_root / "data" / "dataset" / "staging" / f"{job_id}.jsonl").resolve()
    )
    return DatasetJobPaths(
        job_dir=job_dir,
        manifest=job_dir / "manifest.json",
        checkpoint=job_dir / "checkpoint.json",
        errors=job_dir / "errors.jsonl",
        output=output,
    )


def dataset_record_paths(project_root: Path) -> list[Path]:
    base = project_root / "data" / "dataset"
    paths: list[Path] = []
    for state in ("accepted", "needs_revision", "rejected", "staging"):
        directory = base / state
        if not directory.exists():
            continue
        paths.extend(path for path in directory.rglob("*.jsonl") if path.is_file())
        paths.extend(path for path in directory.rglob("*.json") if path.is_file())
    return sorted(set(paths))


def next_dataset_number(existing_ids: set[str], source_type: str) -> int:
    prefix = SOURCE_PREFIX.get(source_type)
    if prefix is None:
        raise DatasetWorkflowError(f"unsupported source_type: {source_type}")
    numbers = []
    for value in existing_ids:
        match = RECORD_ID_RE.fullmatch(value)
        if match and match.group("kind") == "tctr" and match.group("source") == prefix:
            numbers.append(int(match.group("number")))
    next_number = max(numbers, default=0) + 1
    if next_number > 999_999:
        raise DatasetWorkflowError(f"ID range is exhausted for source_type {source_type}")
    return next_number


def prepare_generated_candidate(
    candidate: dict[str, Any],
    *,
    blueprint: dict[str, Any],
    record_id: str,
    identity: ModelIdentity,
    actor_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """Replace provider quality claims with evidence-backed draft state and enforce the blueprint contract."""

    if not isinstance(candidate, dict):
        raise DatasetWorkflowError("provider candidate must be a JSON object")
    if candidate.get("id") != record_id:
        raise DatasetWorkflowError("provider returned an unexpected record ID")
    for version_field in ("schema_version", "tool_registry_version"):
        if candidate.get(version_field) != blueprint.get(version_field):
            raise DatasetWorkflowError(f"provider changed {version_field}")

    metadata = candidate.get("metadata")
    if not isinstance(metadata, dict):
        raise DatasetWorkflowError("provider candidate has no metadata object")
    blueprint_metadata = blueprint["metadata"]
    for field in ("main_category", "source_type", "domain", "difficulty"):
        if metadata.get(field) != blueprint_metadata[field]:
            raise DatasetWorkflowError(f"provider changed blueprint metadata.{field}")
    if sorted(metadata.get("secondary_tags", [])) != sorted(blueprint_metadata["secondary_tags"]):
        raise DatasetWorkflowError("provider changed blueprint metadata.secondary_tags")

    exposed_names = _exposed_tool_names(candidate)
    if sorted(exposed_names) != sorted(blueprint["available_tools"]):
        raise DatasetWorkflowError("provider changed the blueprint available_tools set")
    actual_calls = _actual_expected_calls(candidate)
    expected_calls = copy.deepcopy(blueprint["expected_tool_calls"])
    if blueprint["execution_order"] == "parallel":
        actual_calls = _sort_calls(actual_calls)
        expected_calls = _sort_calls(expected_calls)
    if actual_calls != expected_calls:
        raise DatasetWorkflowError("provider tool calls do not match blueprint expected_tool_calls")
    if blueprint["expected_tool_result"] is not None:
        actual_pairs = _actual_call_result_pairs(candidate)
        expected_results = (
            [blueprint["expected_tool_result"]]
            if len(blueprint["expected_tool_calls"]) == 1
            else blueprint["expected_tool_result"]
        )
        if not isinstance(expected_results, list):
            raise DatasetWorkflowError("multi-tool blueprint expected_tool_result must be an array")
        expected_pairs = [
            {"function": copy.deepcopy(call["function"]), "result": copy.deepcopy(result)}
            for call, result in zip(blueprint["expected_tool_calls"], expected_results, strict=True)
        ]
        if blueprint["execution_order"] == "parallel":
            actual_pairs = _sort_calls(actual_pairs)
            expected_pairs = _sort_calls(expected_pairs)
        if actual_pairs != expected_pairs:
            raise DatasetWorkflowError("provider tool results do not match blueprint expected_tool_result")

    prepared = copy.deepcopy(candidate)
    target_metadata = prepared["metadata"]
    provenance = copy.deepcopy(blueprint_metadata["provenance"])
    provenance["generator_model"] = identity.model
    provenance["generator_version"] = identity.model_version
    provenance["transformation_history"].append(
        {
            "action": "generated_from_blueprint",
            "timestamp": generated_at,
            "actor_id": actor_id,
            "details": (
                f"blueprint={blueprint['id']}; provider={identity.provider}; "
                f"model={identity.model}; role={identity.role}"
            ),
        }
    )
    target_metadata["provenance"] = provenance
    has_tool_calls = bool(expected_calls)
    target_metadata["execution"] = {
        "type": blueprint_metadata["intended_execution_type"] if has_tool_calls else "not_applicable",
        "status": "not_called",
    }
    target_metadata["validation"] = {
        "json": "passed",
        "schema": "passed",
        "tool_call": "passed" if has_tool_calls else "not_applicable",
        "execution": "not_run" if has_tool_calls else "not_applicable",
        "semantic": "not_run",
        "turn_level": "passed" if blueprint_metadata["main_category"] == "multi_turn" else "not_applicable",
        "language": "not_run",
        "duplicate": "not_run",
    }
    target_metadata["review"] = {
        "status": "needs_revision",
        "reviewer_ids": [],
        "notes": f"Generated from {blueprint['id']}; quality gates and human review remain required.",
        "contributor_id": actor_id,
        "requires_two_reviewers": bool(
            blueprint_metadata["main_category"] == "multi_tool"
            or "sequential_tool" in blueprint_metadata["secondary_tags"]
        ),
        "history": [],
    }
    return prepared


def _exposed_tool_names(candidate: dict[str, Any]) -> list[str]:
    try:
        return [tool["function"]["name"] for tool in candidate["tools"]]
    except (KeyError, TypeError) as exc:
        raise DatasetWorkflowError("provider candidate contains invalid tool definitions") from exc


def _actual_expected_calls(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    try:
        messages = candidate["messages"]
        for message in messages:
            if message.get("role") != "assistant" or "tool_calls" not in message:
                continue
            for call in message["tool_calls"]:
                calls.append({"function": copy.deepcopy(call["function"])})
    except (KeyError, TypeError) as exc:
        raise DatasetWorkflowError("provider candidate contains invalid messages or tool calls") from exc
    return calls


def _actual_call_result_pairs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    results: dict[str, Any] = {}
    try:
        for message in candidate["messages"]:
            if message.get("role") == "assistant" and "tool_calls" in message:
                for call in message["tool_calls"]:
                    calls.append((call["id"], copy.deepcopy(call["function"])))
            elif message.get("role") == "tool":
                results[message["tool_call_id"]] = json.loads(message["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DatasetWorkflowError("provider candidate contains invalid tool-result messages") from exc
    missing = [call_id for call_id, _ in calls if call_id not in results]
    if missing:
        raise DatasetWorkflowError("provider candidate is missing blueprint tool results")
    return [
        {"function": function, "result": copy.deepcopy(results[call_id])}
        for call_id, function in calls
    ]


def _sort_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(calls, key=lambda call: json.dumps(call, ensure_ascii=False, sort_keys=True))
