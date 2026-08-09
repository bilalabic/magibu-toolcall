"""Evidence-backed automatic quality gates for dataset drafts."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from threading import Lock
from typing import Any

from tool_call_tr.deduplication import (
    DuplicateReport,
    SemanticSimilarity,
    combined_query_schema_hash,
    exact_query_hash,
    normalized_query_hash,
    tool_schema_fingerprint,
)
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
from tool_call_tr.generation.providers import ProviderError, RecordQualityJudge
from tool_call_tr.semantic import cosine_similarity
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


@dataclass(slots=True)
class _TokenBudget:
    limit: int | None
    accounted: int = 0
    observed: int = 0
    reserved: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)

    def reserve(self, estimate: int) -> bool:
        with self.lock:
            if self.limit is not None and self.accounted + self.reserved + estimate > self.limit:
                return False
            self.reserved += estimate
            return True

    def consume(self, actual: int | None, estimate: int) -> None:
        with self.lock:
            self.reserved -= estimate
            self.accounted += max(estimate, actual or 0)
            if actual is not None:
                self.observed += actual


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
    judge: RecordQualityJudge | None = None,
    judge_provider: str = "none",
    production_judge: bool = False,
    escalation_judge: RecordQualityJudge | None = None,
    escalation_sample_rate: float = 0.0,
    judge_max_workers: int = 1,
    judge_token_budget: int | None = None,
    escalation_token_budget: int | None = None,
    allow_real_api: bool = False,
    timestamp: str | None = None,
) -> QualityResult:
    """Recompute automatic gates without making or implying a human acceptance decision."""

    if not 0.0 <= semantic_threshold <= 1.0:
        raise QualityError("semantic threshold must be between 0 and 1")
    if production_semantic and semantic is None:
        raise QualityError("production semantic mode requires a configured similarity provider")
    if production_judge and judge is None:
        raise QualityError("production judge mode requires a configured quality judge")
    if not 0.0 <= escalation_sample_rate <= 1.0:
        raise QualityError("escalation sample rate must be between 0 and 1")
    if escalation_judge is None and escalation_sample_rate:
        raise QualityError("escalation sampling requires an escalation judge")
    if not 1 <= judge_max_workers <= 32:
        raise QualityError("judge_max_workers must be between 1 and 32")
    if judge_token_budget is not None and judge_token_budget < 1:
        raise QualityError("judge token budget must be positive")
    if escalation_token_budget is not None and escalation_token_budget < 1:
        raise QualityError("escalation token budget must be positive")
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
    judge_evidence: dict[str, dict[str, Any]] = {}
    now = timestamp or datetime.now(timezone.utc).isoformat()
    semantic_model = getattr(getattr(semantic, "provider", None), "model", None)
    primary_budget = _TokenBudget(judge_token_budget)
    escalation_budget = _TokenBudget(escalation_token_budget)

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

    semantic_statuses, judge_evidence = _judge_records(
        updated,
        judge=judge,
        judge_provider=judge_provider,
        production_judge=production_judge,
        escalation_judge=escalation_judge,
        escalation_sample_rate=escalation_sample_rate,
        primary_budget=primary_budget,
        escalation_budget=escalation_budget,
        max_workers=judge_max_workers,
    )
    for record in updated:
        record["metadata"]["validation"]["semantic"] = semantic_statuses[record["id"]]

    pair_reports, duplicate_state, duplicate_summary = _scan_duplicates(
        updated,
        references,
        semantic=semantic,
        production_semantic=production_semantic,
        semantic_threshold=semantic_threshold,
    )
    for record in updated:
        state = duplicate_state[record["id"]]
        if state["duplicate"]:
            duplicate_status = "failed"
        elif state["comparisons_required"] == 0:
            duplicate_status = "passed"
        elif production_semantic and state["comparisons_evaluated"] == state["comparisons_required"]:
            duplicate_status = "passed"
        else:
            duplicate_status = "not_run"
        record["metadata"]["validation"]["duplicate"] = duplicate_status
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
                    f"judge_provider={judge_provider}; judge_model={getattr(judge, 'model', None) or 'none'}; "
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
                "judge_evidence": judge_evidence[record["id"]],
            }
        )
    report = {
        "quality_version": "0.2.0",
        "actor_id": actor_id,
        "created_at": now,
        "semantic": {
            "provider": semantic_provider,
            "model": semantic_model,
            "production": production_semantic,
            "threshold": semantic_threshold,
        },
        "judge": {
            "provider": judge_provider,
            "model": getattr(judge, "model", None),
            "production": production_judge,
            "escalation_model": getattr(escalation_judge, "model", None),
            "escalation_sample_rate": escalation_sample_rate,
            "max_workers": judge_max_workers,
            "primary_token_budget": judge_token_budget,
            "primary_tokens_used": primary_budget.observed,
            "primary_budget_accounted_tokens": primary_budget.accounted,
            "escalation_token_budget": escalation_token_budget,
            "escalation_tokens_used": escalation_budget.observed,
            "escalation_budget_accounted_tokens": escalation_budget.accounted,
        },
        "records": record_reports,
        "duplicate_pairs": [item.to_dict() for item in pair_reports],
        "duplicate_scan": duplicate_summary,
        "summary": {
            "records_checked": len(updated),
            "reference_records": len(references),
            "pairs_checked": duplicate_summary["pairs_checked"],
            "duplicate_findings": len(pair_reports),
            "records_with_automatic_failures": sum(bool(item["automatic_failures"]) for item in record_reports),
            "records_with_model_pass": sum(
                item["validation"]["semantic"] == "passed" for item in record_reports
            ),
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


def _judge_records(
    records: list[dict[str, Any]],
    *,
    judge: RecordQualityJudge | None,
    judge_provider: str,
    production_judge: bool,
    escalation_judge: RecordQualityJudge | None,
    escalation_sample_rate: float,
    primary_budget: _TokenBudget,
    escalation_budget: _TokenBudget,
    max_workers: int,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    def evaluate(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        status, evidence = _judge_record(
            record,
            judge=judge,
            judge_provider=judge_provider,
            production_judge=production_judge,
            escalation_judge=escalation_judge,
            escalation_sample_rate=escalation_sample_rate,
            primary_budget=primary_budget,
            escalation_budget=escalation_budget,
        )
        return record["id"], status, evidence

    if max_workers == 1 or len(records) == 1:
        evaluated = [evaluate(record) for record in records]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="magibu-judge") as executor:
            evaluated = list(executor.map(evaluate, records))
    statuses = {record_id: status for record_id, status, _ in evaluated}
    evidence = {record_id: item for record_id, _, item in evaluated}
    return statuses, evidence


def _judge_record(
    record: dict[str, Any],
    *,
    judge: RecordQualityJudge | None,
    judge_provider: str,
    production_judge: bool,
    escalation_judge: RecordQualityJudge | None,
    escalation_sample_rate: float,
    primary_budget: _TokenBudget,
    escalation_budget: _TokenBudget,
) -> tuple[str, dict[str, Any]]:
    if judge is None:
        return "not_run", {"status": "not_run", "reason": "quality judge was not selected"}

    primary, failure = _call_judge(record, judge=judge, budget=primary_budget)
    if failure is not None:
        return "failed", {
            "status": "failed",
            "provider": judge_provider,
            "model": judge.model,
            "primary": failure,
            "escalation": None,
        }
    primary_value = primary.value
    should_escalate = escalation_judge is not None and (
        primary_value["verdict"] != "pass"
        or _sample_record(record["id"], escalation_sample_rate)
    )
    escalation = None
    escalation_failure = None
    if should_escalate and escalation_judge is not None:
        escalation, escalation_failure = _call_judge(
            record,
            judge=escalation_judge,
            budget=escalation_budget,
        )

    primary_pass = _judgment_passes(primary_value)
    escalation_pass = escalation is None or _judgment_passes(escalation.value)
    certified = production_judge and primary_pass and escalation_pass and escalation_failure is None
    status = "passed" if certified else "failed" if production_judge else "not_run"
    evidence = {
        "status": status,
        "provider": judge_provider,
        "model": judge.model,
        "rubric_version": "dataset-quality-0.1.0",
        "primary": _response_evidence(primary),
        "escalation": (
            escalation_failure
            if escalation_failure is not None
            else _response_evidence(escalation) if escalation is not None else None
        ),
        "agreement": (
            None
            if escalation is None
            else primary.value["verdict"] == escalation.value["verdict"]
        ),
    }
    return status, evidence


def _call_judge(
    record: dict[str, Any],
    *,
    judge: RecordQualityJudge,
    budget: _TokenBudget,
):
    estimate = _estimated_judge_tokens(record, judge)
    if not budget.reserve(estimate):
        return None, {
            "status": "token_budget_exhausted",
            "estimated_tokens": estimate,
            "tokens_accounted_before_request": budget.accounted,
            "token_budget": budget.limit,
        }
    try:
        response = judge.judge_record(record)
    except ProviderError as exc:
        budget.consume(None, estimate)
        return None, {
            "status": "provider_error",
            "error_type": type(exc).__name__,
            "status_code": exc.status_code,
            "retryable": exc.retryable,
        }
    actual = response.usage.get("total_tokens") if response.usage else None
    budget.consume(actual, estimate)
    return response, None


def _estimated_judge_tokens(record: dict[str, Any], judge: RecordQualityJudge) -> int:
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    provider = getattr(judge, "provider", judge)
    max_output = getattr(provider, "max_output_tokens", 1200)
    return math.ceil(len(serialized) / 2) + int(max_output) + 400


def _judgment_passes(value: dict[str, Any]) -> bool:
    return bool(
        value["verdict"] == "pass"
        and min(value["scores"].values()) >= 4
        and not any(issue["severity"] in {"major", "critical"} for issue in value["issues"])
    )


def _response_evidence(response) -> dict[str, Any]:
    return {
        "verdict": response.value["verdict"],
        "scores": copy.deepcopy(response.value["scores"]),
        "issues": copy.deepcopy(response.value["issues"]),
        "summary": response.value["summary"],
        "requested_model": response.identity.model,
        "response_model": response.identity.model_version,
        "attempts": response.attempts,
        "usage": copy.deepcopy(response.usage),
        "request_id": response.request_id,
        "system_fingerprint": response.system_fingerprint,
    }


def _sample_record(record_id: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    bucket = int(hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:12], 16) / float(16**12)
    return bucket < sample_rate


@dataclass(frozen=True, slots=True)
class _DuplicateSignature:
    record: dict[str, Any]
    query: str
    exact_hash: str
    normalized_hash: str
    schema_hashes: tuple[str, ...]
    combined_hash: str
    source_key: tuple[str, str] | None


def _scan_duplicates(
    records: list[dict[str, Any]],
    references: list[dict[str, Any]],
    *,
    semantic: SemanticSimilarity | None,
    production_semantic: bool,
    semantic_threshold: float,
) -> tuple[list[DuplicateReport], dict[str, dict[str, int | bool]], dict[str, int]]:
    state: dict[str, dict[str, int | bool]] = {
        record["id"]: {
            "duplicate": False,
            "comparisons_required": 0,
            "comparisons_evaluated": 0,
        }
        for record in records
    }
    reports: list[DuplicateReport] = []
    signatures = [_duplicate_signature(record) for record in [*records, *references]]
    record_signatures = signatures[:len(records)]
    reference_signatures = signatures[len(records):]
    vector_by_query: dict[str, list[float]] | None = None
    if semantic is not None and hasattr(semantic, "vectors"):
        unique_queries = list(dict.fromkeys(signature.query for signature in signatures))
        vectors = semantic.vectors(unique_queries)  # type: ignore[attr-defined]
        vector_by_query = dict(zip(unique_queries, vectors, strict=True))

    pairs_checked = 0
    semantic_comparisons = 0
    for left_index, left in enumerate(record_signatures):
        pairs = [
            *((right, [left.record["id"], right.record["id"]]) for right in record_signatures[left_index + 1:]),
            *((right, [left.record["id"]]) for right in reference_signatures),
        ]
        for right, affected_ids in pairs:
            pairs_checked += 1
            report = _deterministic_duplicate_report(left, right)
            if report.decision != "duplicate":
                for record_id in affected_ids:
                    state[record_id]["comparisons_required"] = int(state[record_id]["comparisons_required"]) + 1
                if semantic is not None:
                    score = (
                        cosine_similarity(vector_by_query[left.query], vector_by_query[right.query])
                        if vector_by_query is not None
                        else semantic.score(left.query, right.query)
                    )
                    semantic_comparisons += 1
                    for record_id in affected_ids:
                        state[record_id]["comparisons_evaluated"] = int(state[record_id]["comparisons_evaluated"]) + 1
                    report = DuplicateReport(
                        report.left_id,
                        report.right_id,
                        report.exact_query,
                        report.normalized_query,
                        report.entity_shape,
                        report.tool_schema_match,
                        report.combined_match,
                        report.source_example_match,
                        score,
                        "possible_duplicate" if score >= semantic_threshold else "distinct",
                    )
            if report.decision in {"duplicate", "possible_duplicate"}:
                for record_id in affected_ids:
                    state[record_id]["duplicate"] = True
                reports.append(report)
    return reports, state, {
        "pairs_checked": pairs_checked,
        "semantic_comparisons": semantic_comparisons,
        "findings_retained": len(reports),
    }


def _duplicate_signature(record: dict[str, Any]) -> _DuplicateSignature:
    query = "\n".join(
        message["content"]
        for message in record.get("messages", [])
        if message.get("role") == "user"
    )
    schemas = [tool["function"]["parameters"] for tool in record.get("tools", [])]
    provenance = record["metadata"]["provenance"]
    source_key = None
    if provenance.get("source_dataset") is not None and provenance.get("source_example_id") is not None:
        source_key = (provenance["source_dataset"], provenance["source_example_id"])
    return _DuplicateSignature(
        record=record,
        query=query,
        exact_hash=exact_query_hash(query),
        normalized_hash=normalized_query_hash(query),
        schema_hashes=tuple(sorted(tool_schema_fingerprint(schema) for schema in schemas)),
        combined_hash=combined_query_schema_hash(query, schemas),
        source_key=source_key,
    )


def _deterministic_duplicate_report(
    left: _DuplicateSignature,
    right: _DuplicateSignature,
) -> DuplicateReport:
    exact = left.exact_hash == right.exact_hash
    normalized = left.normalized_hash == right.normalized_hash
    schema_match = left.schema_hashes == right.schema_hashes
    combined = left.combined_hash == right.combined_hash
    source_match = left.source_key is not None and left.source_key == right.source_key
    return DuplicateReport(
        left.record["id"],
        right.record["id"],
        exact,
        normalized,
        False,
        schema_match,
        combined,
        source_match,
        None,
        "duplicate" if exact or combined or source_match else "needs_semantic_review",
    )
