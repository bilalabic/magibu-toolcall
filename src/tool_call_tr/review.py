"""Human review state transitions and validated accepted-only export."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from tool_call_tr.validation import RuleBasedValidator


ALLOWED_TRANSITIONS = {
    "needs_revision": {"needs_revision", "accepted", "rejected"},
    "rejected": {"needs_revision", "rejected"},
    "accepted": {"accepted", "needs_revision", "rejected"},
}


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
    new_status: str,
    notes: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if reviewer_role not in {"language", "technical"}:
        raise ReviewError(f"unsupported reviewer role: {reviewer_role}")
    review = record["metadata"]["review"]
    current_status = review["status"]
    if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ReviewError(f"invalid review transition: {current_status} -> {new_status}")
    contributor_id = review.get("contributor_id")
    if new_status == "accepted" and contributor_id == reviewer_id:
        raise ReviewError("a contributor cannot provide final approval for their own record")

    updated = copy.deepcopy(record)
    target = updated["metadata"]["review"]
    if reviewer_id not in target["reviewer_ids"]:
        target["reviewer_ids"].append(reviewer_id)
    target.setdefault("history", []).append(
        {
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "from_status": current_status,
            "to_status": new_status,
            "notes": notes,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
    )
    target["status"] = new_status
    target["notes"] = notes
    if new_status == "accepted":
        if not target["reviewer_ids"]:
            raise ReviewError("accepted records require a reviewer")
        if record_requires_two_reviewers(updated):
            if len(target["reviewer_ids"]) < 2:
                raise ReviewError("this record requires two distinct reviewers")
            roles = {event["reviewer_role"] for event in target["history"]}
            if not {"language", "technical"} <= roles:
                raise ReviewError("two-reviewer acceptance requires language and technical perspectives")
    return updated


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

