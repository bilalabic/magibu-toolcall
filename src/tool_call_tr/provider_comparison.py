"""Evidence-backed Flash/Pro generation comparison for the frozen pilot blueprints."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Protocol

from tool_call_tr.dataset_workflow import (
    build_candidate_from_language_plan,
    prepare_generated_candidate,
)
from tool_call_tr.generation.providers import (
    ModelIdentity,
    ProviderResponse,
    RecordQualityJudge,
    RetryPolicy,
    run_language_plan_with_retry,
)
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


COMPARISON_VERSION = "flash-pro-pilot-0.1.0"
FLASH_MODEL = "deepseek-v4-flash"
PRO_MODEL = "deepseek-v4-pro"


class LanguagePlanGenerator(Protocol):
    model: str | None

    def generate_language_plan(self, blueprint: dict[str, Any]) -> ProviderResponse:
        ...


class RetryingLanguagePlanGenerator:
    def __init__(self, provider: LanguagePlanGenerator, policy: RetryPolicy) -> None:
        self.provider = provider
        self.policy = policy
        self.model = provider.model

    def generate_language_plan(self, blueprint: dict[str, Any]) -> ProviderResponse:
        return run_language_plan_with_retry(
            self.provider,
            blueprint,
            self.policy,
            sleep=time.sleep,
        )


@dataclass(frozen=True, slots=True)
class GenerationComparisonResult:
    report: dict[str, Any]
    candidates: dict[str, list[dict[str, Any]]]


def filter_blueprints_by_id(
    blueprints: list[dict[str, Any]],
    requested_ids: list[str],
) -> list[dict[str, Any]]:
    """Select named blueprints in source order and fail on unknown IDs."""
    if not requested_ids:
        return blueprints
    requested = set(requested_ids)
    selected = [blueprint for blueprint in blueprints if blueprint.get("id") in requested]
    found = {blueprint.get("id") for blueprint in selected}
    missing = sorted(requested - found)
    if missing:
        raise ValueError("unknown comparison blueprint ID(s): " + ", ".join(missing))
    return selected


def run_generation_comparison(
    blueprints: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    generators: dict[str, LanguagePlanGenerator],
    actor_id: str,
    judge: RecordQualityJudge | None = None,
    generated_at: str | None = None,
    max_workers: int = 1,
) -> GenerationComparisonResult:
    if not blueprints:
        raise ValueError("generation comparison requires at least one blueprint")
    if not generators:
        raise ValueError("generation comparison requires at least one model")
    if not 1 <= max_workers <= 32:
        raise ValueError("max_workers must be between 1 and 32")
    validator = RuleBasedValidator(registry=registry)
    for blueprint in blueprints:
        report = validator.validate_record("blueprint", blueprint)
        if not report.valid:
            raise ValueError(f"invalid comparison blueprint {blueprint.get('id')}: {report.human()}")
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    assigned = _assign_record_ids(blueprints)
    candidate_outputs: dict[str, list[dict[str, Any]]] = {}
    model_reports: dict[str, Any] = {}

    for model, generator in generators.items():
        def process(item: tuple[dict[str, Any], str]) -> tuple[dict[str, Any], dict[str, Any] | None]:
            blueprint, record_id = item
            return _compare_one(
                blueprint,
                record_id=record_id,
                registry=registry,
                validator=validator,
                generator=generator,
                actor_id=actor_id,
                generated_at=timestamp,
                judge=judge,
            )

        if max_workers == 1:
            completed = [process(item) for item in assigned]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                completed = list(pool.map(process, assigned))
        entries = [entry for entry, _ in completed]
        candidates = [candidate for _, candidate in completed if candidate is not None]
        candidate_outputs[model] = candidates
        model_reports[model] = _summarize_model(model, entries)

    report = {
        "comparison_version": COMPARISON_VERSION,
        "generated_at": timestamp,
        "actor_id": actor_id,
        "blueprint_count": len(blueprints),
        "models": model_reports,
        "decision": recommend_generation_policy(model_reports, sample_size=len(blueprints), judge_enabled=judge is not None),
    }
    return GenerationComparisonResult(report, candidate_outputs)


def _compare_one(
    blueprint: dict[str, Any],
    *,
    record_id: str,
    registry: ToolRegistry,
    validator: RuleBasedValidator,
    generator: LanguagePlanGenerator,
    actor_id: str,
    generated_at: str,
    judge: RecordQualityJudge | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    entry: dict[str, Any] = {
        "blueprint_id": blueprint["id"],
        "record_id": record_id,
        "status": "failed",
        "error": None,
        "generation": None,
        "judge": None,
    }
    try:
        response = generator.generate_language_plan(copy.deepcopy(blueprint))
        candidate = build_candidate_from_language_plan(
            response.value,
            blueprint=blueprint,
            record_id=record_id,
            registry=registry,
        )
        candidate = prepare_generated_candidate(
            candidate,
            blueprint=blueprint,
            record_id=record_id,
            identity=response.identity,
            actor_id=actor_id,
            generated_at=generated_at,
            provider_usage=response.usage,
            provider_request_id=response.request_id,
            provider_system_fingerprint=response.system_fingerprint,
            provider_attempts=response.attempts,
        )
        validation = validator.validate_record("dataset", candidate)
        if not validation.valid:
            raise ValueError(validation.human())
        entry["generation"] = _response_evidence(response)
        entry["status"] = "passed"
        if judge is not None:
            try:
                judgment = judge.judge_record(candidate)
                entry["judge"] = {
                    "status": "passed",
                    "verdict": judgment.value["verdict"],
                    "scores": judgment.value["scores"],
                    "issues": judgment.value["issues"],
                    "summary": judgment.value["summary"],
                    "evidence": _response_evidence(judgment),
                }
            except Exception as exc:
                entry["judge"] = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return entry, candidate
    except Exception as exc:  # comparison keeps independent samples and records bounded errors
        entry["error"] = f"{type(exc).__name__}: {exc}"
        return entry, None


def _response_evidence(response: ProviderResponse) -> dict[str, Any]:
    identity: ModelIdentity = response.identity
    return {
        "provider": identity.provider,
        "configured_model": identity.model,
        "response_model": identity.model_version,
        "role": identity.role,
        "attempts": response.attempts,
        "usage": copy.deepcopy(response.usage),
        "request_id": response.request_id,
        "system_fingerprint": response.system_fingerprint,
    }


def _assign_record_ids(blueprints: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
    counters: Counter[str] = Counter()
    values = []
    for blueprint in blueprints:
        source_type = blueprint["metadata"]["source_type"]
        prefix = {"original_turkish": "ot", "turkey_native": "tn"}.get(source_type)
        if prefix is None:
            raise ValueError(f"paused or unsupported comparison source type: {source_type}")
        counters[source_type] += 1
        values.append((blueprint, f"tctr_{prefix}_{counters[source_type]:06d}"))
    return values


def _summarize_model(model: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    generation_passes = [entry for entry in entries if entry["status"] == "passed"]
    judgments = [
        entry["judge"]
        for entry in generation_passes
        if entry["judge"] is not None and entry["judge"].get("status") == "passed"
    ]
    judge_failures = sum(
        entry["judge"] is not None and entry["judge"].get("status") == "failed"
        for entry in generation_passes
    )
    verdicts = Counter(judgment["verdict"] for judgment in judgments)
    dimensions = sorted({dimension for judgment in judgments for dimension in judgment["scores"]})
    mean_scores = {
        dimension: round(
            sum(judgment["scores"][dimension] for judgment in judgments) / len(judgments),
            4,
        )
        for dimension in dimensions
    } if judgments else {}
    generation_usage = _sum_usage(
        entry["generation"]["usage"]
        for entry in generation_passes
        if entry["generation"] is not None
    )
    judge_usage = _sum_usage(
        judgment["evidence"]["usage"]
        for judgment in judgments
    )
    return {
        "model": model,
        "total": len(entries),
        "generation_passed": len(generation_passes),
        "generation_failed": len(entries) - len(generation_passes),
        "judge_verdicts": dict(sorted(verdicts.items())),
        "judge_failed": judge_failures,
        "mean_scores": mean_scores,
        "mean_overall_score": (
            round(sum(mean_scores.values()) / len(mean_scores), 4) if mean_scores else None
        ),
        "generation_usage": generation_usage,
        "judge_usage": judge_usage,
        "records": entries,
    }


def _sum_usage(usages: Any) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for usage in usages:
        if isinstance(usage, dict):
            totals.update({key: value for key, value in usage.items() if isinstance(value, int)})
    return dict(sorted(totals.items()))


def recommend_generation_policy(
    model_reports: dict[str, Any],
    *,
    sample_size: int,
    judge_enabled: bool,
) -> dict[str, Any]:
    rules = {
        "minimum_sample_size": 30,
        "zero_generation_failures": True,
        "minimum_flash_overall_score": 4.0,
        "all_flash_judgments_must_pass": True,
        "maximum_flash_score_gap_vs_pro": 0.15,
        "maximum_flash_pass_count_gap_vs_pro": 1,
    }
    if sample_size < rules["minimum_sample_size"]:
        return {
            "status": "insufficient_sample",
            "flash_first": False,
            "pro_fallback": True,
            "rules": rules,
            "reasons": [f"at least 30 paired blueprints are required; observed {sample_size}"],
        }
    flash = model_reports.get(FLASH_MODEL)
    pro = model_reports.get(PRO_MODEL)
    if flash is None or pro is None:
        return {
            "status": "incomplete_model_pair",
            "flash_first": False,
            "pro_fallback": True,
            "rules": rules,
            "reasons": ["both deepseek-v4-flash and deepseek-v4-pro are required"],
        }
    reasons = []
    if flash["generation_failed"]:
        reasons.append(f"Flash generation failures: {flash['generation_failed']}")
    if pro["generation_failed"]:
        reasons.append(f"Pro generation failures: {pro['generation_failed']}")
    if not judge_enabled:
        reasons.append("OpenAI judge evidence is required")
    else:
        if flash["judge_failed"] or pro["judge_failed"]:
            reasons.append(
                f"judge failures are present: Flash={flash['judge_failed']}, Pro={pro['judge_failed']}"
            )
        flash_score = flash["mean_overall_score"]
        pro_score = pro["mean_overall_score"]
        if flash_score is None or pro_score is None:
            reasons.append("paired judge scores are incomplete")
        else:
            if flash_score < rules["minimum_flash_overall_score"]:
                reasons.append(f"Flash mean score {flash_score} is below 4.0")
            if pro_score - flash_score > rules["maximum_flash_score_gap_vs_pro"]:
                reasons.append(f"Flash trails Pro by {round(pro_score - flash_score, 4)} points")
        flash_passes = flash["judge_verdicts"].get("pass", 0)
        pro_passes = pro["judge_verdicts"].get("pass", 0)
        if flash_passes != sample_size:
            reasons.append(
                f"Flash must pass every judged blueprint: passed {flash_passes} of {sample_size}"
            )
        if pro_passes - flash_passes > rules["maximum_flash_pass_count_gap_vs_pro"]:
            reasons.append(f"Flash has {pro_passes - flash_passes} fewer judge passes than Pro")
    accepted = not reasons
    return {
        "status": "accepted" if accepted else "rejected",
        "flash_first": accepted,
        "pro_fallback": True,
        "fallback_conditions": [
            "provider error or invalid JSON language plan",
            "unexpected-script or reasoning-tag leakage",
            "deterministic dataset-schema failure",
            "OpenAI quality verdict other than pass during gated production",
        ],
        "rules": rules,
        "reasons": reasons,
    }
