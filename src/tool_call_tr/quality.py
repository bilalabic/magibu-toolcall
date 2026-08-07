"""Evidence-backed automatic quality gates for dataset drafts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from tool_call_tr.deduplication import DuplicateReport, SemanticSimilarity, compare_records
from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    HttpJsonAdapter,
    LocalExecutableAdapter,
    MockAdapter,
    StatefulSimulationAdapter,
)
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ACTIVE_SOURCE_TYPES = {"original_turkish", "turkey_native"}


class QualityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QualityResult:
    records: list[dict[str, Any]]
    report: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.report["summary"]["records_with_automatic_failures"] == 0


def run_dataset_quality(
    records: list[dict[str, Any]],
    *,
    references: list[dict[str, Any]],
    registry: ToolRegistry,
    actor_id: str,
    semantic: SemanticSimilarity | None = None,
    semantic_provider: str = "none",
    production_semantic: bool = False,
    semantic_threshold: float = 0.9,
    allow_real_api: bool = False,
    timestamp: str | None = None,
) -> QualityResult:
    """Recompute automatic gates without making or implying a human acceptance decision."""

    if not 0.0 <= semantic_threshold <= 1.0:
        raise QualityError("semantic threshold must be between 0 and 1")
    if production_semantic and semantic is None:
        raise QualityError("production semantic mode requires a configured similarity provider")
    if not records:
        raise QualityError("quality input cannot be empty")

    validator = RuleBasedValidator(registry=registry)
    _validate_inputs(records, validator=validator, label="quality input", require_draft=True)
    _validate_inputs(references, validator=validator, label="reference corpus", require_draft=False)
    unaccepted_references = [
        record["id"] for record in references
        if record["metadata"]["review"]["status"] != "accepted"
    ]
    if unaccepted_references:
        raise QualityError(
            "reference corpus must contain accepted records only: " + ", ".join(unaccepted_references)
        )
    id_collisions = sorted({record["id"] for record in records} & {record["id"] for record in references})
    if id_collisions:
        raise QualityError("quality input IDs already exist in reference corpus: " + ", ".join(id_collisions))
    updated = copy.deepcopy(records)
    record_evidence: dict[str, list[dict[str, Any]]] = {}
    now = timestamp or datetime.now(timezone.utc).isoformat()
    semantic_model = getattr(getattr(semantic, "provider", None), "model", None)

    for record in updated:
        metadata = record["metadata"]
        if metadata["source_type"] not in ACTIVE_SOURCE_TYPES:
            raise QualityError(
                f"record {record['id']} uses paused source_type {metadata['source_type']}"
            )
        call_count = _tool_call_count(record)
        metadata["validation"].update(
            {
                "json": "passed",
                "schema": "passed",
                "tool_call": "passed" if call_count else "not_applicable",
                "turn_level": "passed" if metadata["main_category"] == "multi_turn" else "not_applicable",
                "execution": "not_run" if call_count else "not_applicable",
                "semantic": "not_run",
                "duplicate": "passed",
            }
        )
        if not _has_approved_language_review(record):
            metadata["validation"]["language"] = "not_run"
        execution, evidence = _verify_execution(record, registry=registry, allow_real_api=allow_real_api)
        metadata["execution"] = execution
        metadata["validation"]["execution"] = (
            "not_applicable"
            if execution["type"] == "not_applicable"
            else "not_run"
            if execution["status"] == "not_called"
            else "passed"
            if execution["status"] == "passed"
            else "failed"
        )
        record_evidence[record["id"]] = evidence

    pair_reports, semantic_state = _scan_duplicates(
        updated,
        references,
        semantic=semantic,
        production_semantic=production_semantic,
        semantic_threshold=semantic_threshold,
    )
    for record in updated:
        state = semantic_state[record["id"]]
        record["metadata"]["validation"]["duplicate"] = "failed" if state["duplicate"] else "passed"
        if state["semantic_required"] == 0:
            semantic_status = "not_applicable"
        elif state["semantic_failed"]:
            semantic_status = "failed"
        elif production_semantic and state["semantic_evaluated"] == state["semantic_required"]:
            semantic_status = "passed"
        else:
            semantic_status = "not_run"
        record["metadata"]["validation"]["semantic"] = semantic_status
        validation = record["metadata"]["validation"]
        automatic_failures = [
            name for name, status in validation.items()
            if name != "language" and status == "failed"
        ]
        pending = [name for name, status in validation.items() if status == "not_run"]
        record["metadata"]["provenance"]["transformation_history"].append(
            {
                "action": "automatic_quality_checked",
                "timestamp": now,
                "actor_id": actor_id,
                "details": (
                    f"semantic_provider={semantic_provider}; semantic_model={semantic_model or 'none'}; "
                    f"threshold={semantic_threshold}; "
                    f"automatic_failures={','.join(automatic_failures) or 'none'}; "
                    f"pending={','.join(pending) or 'none'}"
                ),
            }
        )
        report = validator.validate_record("dataset", record)
        if not report.valid:
            raise QualityError(f"quality output became invalid for {record['id']}: {report.human()}")

    record_reports = []
    for record in updated:
        validation = record["metadata"]["validation"]
        automatic_failures = [
            name for name, status in validation.items()
            if name != "language" and status == "failed"
        ]
        record_reports.append(
            {
                "record_id": record["id"],
                "execution": copy.deepcopy(record["metadata"]["execution"]),
                "validation": copy.deepcopy(validation),
                "automatic_failures": automatic_failures,
                "pending_gates": [name for name, status in validation.items() if status == "not_run"],
                "execution_evidence": record_evidence[record["id"]],
            }
        )
    report = {
        "quality_version": "0.1.0",
        "actor_id": actor_id,
        "created_at": now,
        "semantic": {
            "provider": semantic_provider,
            "model": semantic_model,
            "production": production_semantic,
            "threshold": semantic_threshold,
        },
        "records": record_reports,
        "duplicate_pairs": [item.to_dict() for item in pair_reports],
        "summary": {
            "records_checked": len(updated),
            "reference_records": len(references),
            "pairs_checked": len(pair_reports),
            "records_with_automatic_failures": sum(bool(item["automatic_failures"]) for item in record_reports),
            "records_pending_human_language_review": sum(
                item["validation"]["language"] == "not_run" for item in record_reports
            ),
        },
    }
    return QualityResult(updated, report)


def write_quality_report(path: Path, report: dict[str, Any], *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise QualityError(f"quality report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_inputs(
    records: list[dict[str, Any]],
    *,
    validator: RuleBasedValidator,
    label: str,
    require_draft: bool,
) -> None:
    seen: set[str] = set()
    failures: list[str] = []
    for record in records:
        record_id = record.get("id") if isinstance(record, dict) else None
        if isinstance(record_id, str) and record_id in seen:
            failures.append(f"duplicate record ID in {label}: {record_id}")
            continue
        if isinstance(record_id, str):
            seen.add(record_id)
        report = validator.validate_record("dataset", record)
        if not report.valid:
            failures.append(report.human())
        if require_draft and isinstance(record, dict) and record.get("metadata", {}).get("review", {}).get("status") == "accepted":
            failures.append(f"accepted record cannot be rewritten by quality workflow: {record_id}")
    if failures:
        raise QualityError("\n".join(failures))


def _tool_call_count(record: dict[str, Any]) -> int:
    return sum(
        len(message.get("tool_calls", []))
        for message in record["messages"]
        if message.get("role") == "assistant"
    )


def _has_approved_language_review(record: dict[str, Any]) -> bool:
    return any(
        event.get("reviewer_role") == "language" and event.get("decision") == "approve"
        for event in record["metadata"]["review"].get("history", [])
    )


def _verify_execution(
    record: dict[str, Any],
    *,
    registry: ToolRegistry,
    allow_real_api: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calls = [
        call
        for message in record["messages"]
        if message.get("role") == "assistant"
        for call in message.get("tool_calls", [])
    ]
    if not calls:
        return {"type": "not_applicable", "status": "not_called"}, []

    execution_type = ExecutionType(record["metadata"]["execution"]["type"])
    if execution_type in {ExecutionType.SANDBOX} or (
        execution_type == ExecutionType.REAL_API and not allow_real_api
    ):
        return {"type": execution_type.value, "status": "not_called"}, [
            {"status": "not_run", "reason": f"{execution_type.value} execution was not authorized"}
        ]

    fixture_ids = sorted({
        fixture_id
        for call in calls
        for fixture_id in registry.by_function_name(call["function"]["name"])["execution"].get("fixture_ids", [])
    })
    adapters = [LocalExecutableAdapter(), StatefulSimulationAdapter()]
    if fixture_ids:
        adapters.append(MockAdapter.from_registry(registry, fixture_ids))
    if allow_real_api:
        for call in calls:
            tool = registry.by_function_name(call["function"]["name"])
            if execution_type == ExecutionType.REAL_API and tool["lifecycle"] != "approved":
                raise QualityError("real API quality execution requires approved registry tools")
        adapters.append(HttpJsonAdapter(registry))
    engine = ExecutionEngine(registry, ExecutionRouter(adapters))
    tool_results = {
        message["tool_call_id"]: message
        for message in record["messages"]
        if message.get("role") == "tool"
    }
    evidence: list[dict[str, Any]] = []
    overall = ExecutionStatus.PASSED
    single_fixture_id: str | None = None
    for call in calls:
        request = ExecutionRequest(
            call["id"],
            call["function"]["name"],
            call["function"]["arguments"],
            execution_type,
        )
        try:
            result = engine.execute(request)
        except Exception as exc:
            result_status = ExecutionStatus.FAILED
            evidence.append(
                {
                    "call_id": call["id"],
                    "function_name": call["function"]["name"],
                    "status": result_status.value,
                    "reason": type(exc).__name__,
                }
            )
            overall = result_status
            continue
        result_status = result.status
        reason = None
        expected_message = tool_results.get(call["id"])
        if result_status == ExecutionStatus.PASSED:
            if expected_message is None:
                result_status = ExecutionStatus.INVALID_RESULT
                reason = "missing_tool_result_message"
            else:
                try:
                    recorded_result = json.loads(expected_message["content"])
                except (KeyError, TypeError, json.JSONDecodeError):
                    result_status = ExecutionStatus.INVALID_RESULT
                    reason = "invalid_tool_result_json"
                else:
                    if recorded_result != result.data:
                        result_status = ExecutionStatus.INVALID_RESULT
                        reason = "recorded_result_mismatch"
        if result_status != ExecutionStatus.PASSED and overall == ExecutionStatus.PASSED:
            overall = result_status
        if result.fixture_id:
            single_fixture_id = result.fixture_id if len(calls) == 1 else None
        item = {
            "call_id": call["id"],
            "function_name": call["function"]["name"],
            "status": result_status.value,
        }
        if reason:
            item["reason"] = reason
        evidence.append(item)
    execution = {"type": execution_type.value, "status": overall.value}
    if single_fixture_id:
        execution["fixture_id"] = single_fixture_id
    if overall != ExecutionStatus.PASSED:
        execution["error_code"] = "quality_execution_failed"
    return execution, evidence


def _scan_duplicates(
    records: list[dict[str, Any]],
    references: list[dict[str, Any]],
    *,
    semantic: SemanticSimilarity | None,
    production_semantic: bool,
    semantic_threshold: float,
) -> tuple[list[DuplicateReport], dict[str, dict[str, int | bool]]]:
    state: dict[str, dict[str, int | bool]] = {
        record["id"]: {
            "duplicate": False,
            "semantic_required": 0,
            "semantic_evaluated": 0,
            "semantic_failed": False,
        }
        for record in records
    }
    reports: list[DuplicateReport] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    for left_index, left in enumerate(records):
        for right in records[left_index + 1:]:
            pairs.append((left, right, [left["id"], right["id"]]))
        for reference in references:
            if left["id"] != reference["id"]:
                pairs.append((left, reference, [left["id"]]))

    for left, right, affected_ids in pairs:
        deterministic = compare_records(left, right, semantic=None, semantic_threshold=semantic_threshold)
        if deterministic.decision == "duplicate":
            report = deterministic
        else:
            for record_id in affected_ids:
                state[record_id]["semantic_required"] = int(state[record_id]["semantic_required"]) + 1
            if semantic is None:
                report = deterministic
            else:
                report = compare_records(
                    left,
                    right,
                    semantic=semantic,
                    semantic_threshold=semantic_threshold,
                )
                for record_id in affected_ids:
                    state[record_id]["semantic_evaluated"] = int(state[record_id]["semantic_evaluated"]) + 1
        if report.decision == "duplicate":
            for record_id in affected_ids:
                state[record_id]["duplicate"] = True
        elif report.decision == "possible_duplicate":
            for record_id in affected_ids:
                state[record_id]["duplicate"] = True
                if production_semantic:
                    state[record_id]["semantic_failed"] = True
        reports.append(report)
    return reports, state
