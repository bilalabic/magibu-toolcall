"""Human review state transitions and validated accepted-only export."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.validation import RuleBasedValidator


REVIEW_DECISIONS = {"approve", "needs_revision", "reject"}


class ReviewError(ValueError):
    pass


def record_requires_two_reviewers(record: dict[str, Any]) -> bool:
    metadata = record["metadata"]
    review = metadata["review"]
    return bool(
        review.get("requires_two_reviewers")
        or metadata["main_category"] == "multi_tool"
        or "sequential_tool" in metadata["secondary_tags"]
    )


def apply_review(
    record: dict[str, Any],
    *,
    reviewer_id: str,
    reviewer_role: str,
    decision: str,
    notes: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if reviewer_role not in {"language", "technical"}:
        raise ReviewError(f"unsupported reviewer role: {reviewer_role}")
    if decision not in REVIEW_DECISIONS:
        raise ReviewError(f"unsupported review decision: {decision}")
    review = record["metadata"]["review"]
    current_status = review["status"]
    if current_status == "rejected" and decision == "approve":
        raise ReviewError("a rejected record must be reopened with needs_revision before approval")
    contributor_id = review.get("contributor_id")
    if decision == "approve" and contributor_id == reviewer_id:
        raise ReviewError("a contributor cannot approve their own record")

    updated = copy.deepcopy(record)
    target = updated["metadata"]["review"]
    if reviewer_id not in target["reviewer_ids"]:
        target["reviewer_ids"].append(reviewer_id)
    if reviewer_role == "language":
        updated["metadata"]["validation"]["language"] = (
            "passed" if decision == "approve" else "failed"
        )
    event = {
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "decision": decision,
        "from_status": current_status,
        "to_status": "needs_revision",
        "notes": notes,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    target.setdefault("history", []).append(event)
    if decision == "reject":
        new_status = "rejected"
    elif decision == "needs_revision":
        new_status = "needs_revision"
    else:
        new_status = "accepted" if _ready_for_acceptance(updated) else "needs_revision"
    event["to_status"] = new_status
    target["status"] = new_status
    target["notes"] = notes
    return updated


def _ready_for_acceptance(record: dict[str, Any]) -> bool:
    validation = record["metadata"]["validation"]
    if any(status in {"failed", "not_run"} for status in validation.values()):
        return False
    latest_by_role: dict[str, dict[str, Any]] = {}
    for event in record["metadata"]["review"].get("history", []):
        latest_by_role[event["reviewer_role"]] = event
    if any(event["decision"] != "approve" for event in latest_by_role.values()):
        return False
    required_roles = {"technical"} if record.get("id", "").startswith("bench_") else {"language"}
    if record_requires_two_reviewers(record):
        required_roles.update({"language", "technical"})
    if not required_roles <= set(latest_by_role):
        return False
    approver_ids = {latest_by_role[role]["reviewer_id"] for role in required_roles}
    return len(approver_ids) == len(required_roles)


def partition_by_review_status(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {"accepted": [], "needs_revision": [], "rejected": []}
    for record in records:
        result[record["metadata"]["review"]["status"]].append(record)
    return result


def export_accepted(
    records: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    validator: RuleBasedValidator,
    kind: str = "dataset",
    overwrite: bool = False,
) -> int:
    if output_path.exists() and not overwrite:
        raise ReviewError(f"output already exists: {output_path}")
    accepted = [copy.deepcopy(record) for record in records if record["metadata"]["review"]["status"] == "accepted"]
    failures = []
    for record in accepted:
        report = validator.validate_record(kind, record)
        if not report.valid:
            failures.append((record.get("id"), report.issues))
    if failures:
        raise ReviewError(f"accepted export blocked by validation failures: {', '.join(str(item[0]) for item in failures)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in accepted)
    output_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return len(accepted)
