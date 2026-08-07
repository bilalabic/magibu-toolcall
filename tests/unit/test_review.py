from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tool_call_tr.registry import ToolRegistry
from tool_call_tr.cli import main
from tool_call_tr.review import (
    ReviewError,
    apply_review,
    export_accepted,
    partition_by_review_status,
    record_requires_two_reviewers,
)
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "dataset" / name).read_text(encoding="utf-8"))


def pending(record: dict, *, contributor: str = "contrib_01") -> dict:
    value = copy.deepcopy(record)
    value["metadata"]["review"] = {
        "status": "needs_revision",
        "reviewer_ids": [],
        "notes": None,
        "contributor_id": contributor,
        "requires_two_reviewers": value["metadata"]["review"].get("requires_two_reviewers", False),
        "history": [],
    }
    return value


def validator() -> RuleBasedValidator:
    return RuleBasedValidator(registry=ToolRegistry.load(ROOT / "registry" / "registry.jsonl"))


def test_simple_review_transition_and_history() -> None:
    reviewed = apply_review(
        pending(load("valid_no_tool.json")), reviewer_id="rev_language_01", reviewer_role="language",
        decision="approve", notes="Dil uygun.", timestamp="2026-08-06T00:00:00+00:00",
    )
    assert reviewed["metadata"]["review"]["status"] == "accepted"
    assert reviewed["metadata"]["review"]["history"][0]["decision"] == "approve"
    assert reviewed["metadata"]["review"]["history"][0]["from_status"] == "needs_revision"


def test_self_final_approval_is_prevented() -> None:
    with pytest.raises(ReviewError, match="own record"):
        apply_review(pending(load("valid_no_tool.json")), reviewer_id="contrib_01", reviewer_role="technical", decision="approve")


def test_two_reviewer_records_require_both_perspectives() -> None:
    record = pending(load("valid_single_tool.json"))
    assert record_requires_two_reviewers(record)
    first = apply_review(record, reviewer_id="rev_language_01", reviewer_role="language", decision="approve")
    assert first["metadata"]["review"]["status"] == "needs_revision"
    accepted = apply_review(first, reviewer_id="rev_technical_01", reviewer_role="technical", decision="approve")
    assert accepted["metadata"]["review"]["status"] == "accepted"
    assert len(accepted["metadata"]["review"]["reviewer_ids"]) == 2


def test_reviewer_approval_does_not_bypass_pending_automatic_gates() -> None:
    record = pending(load("valid_no_tool.json"))
    record["metadata"]["validation"]["semantic"] = "not_run"
    reviewed = apply_review(
        record,
        reviewer_id="rev_language_01",
        reviewer_role="language",
        decision="approve",
    )
    assert reviewed["metadata"]["validation"]["language"] == "passed"
    assert reviewed["metadata"]["review"]["status"] == "needs_revision"


def test_partition_and_accepted_only_export(tmp_path: Path) -> None:
    accepted = load("valid_no_tool.json")
    revision = pending(load("valid_missing_parameter.json"))
    rejected = pending(load("valid_single_tool.json"))
    rejected["metadata"]["review"]["status"] = "rejected"
    partitions = partition_by_review_status([accepted, revision, rejected])
    assert {key: len(value) for key, value in partitions.items()} == {"accepted": 1, "needs_revision": 1, "rejected": 1}
    output = tmp_path / "accepted.jsonl"
    assert export_accepted([accepted, revision, rejected], output, validator=validator()) == 1
    exported = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["id"] for record in exported] == [accepted["id"]]
    with pytest.raises(ReviewError, match="already exists"):
        export_accepted([accepted], output, validator=validator())


def test_invalid_accepted_record_is_never_exported(tmp_path: Path) -> None:
    invalid = load("valid_single_tool.json")
    invalid["messages"][1]["tool_calls"][0]["function"]["arguments"].pop("right")
    with pytest.raises(ReviewError, match="validation failures"):
        export_accepted([invalid], tmp_path / "blocked.jsonl", validator=validator())
    assert not (tmp_path / "blocked.jsonl").exists()


def test_export_cli_is_explicit_and_accepted_only(tmp_path: Path, capsys, access_files) -> None:
    accepted = load("valid_no_tool.json")
    rejected = pending(load("valid_missing_parameter.json"))
    rejected["metadata"]["review"]["status"] = "rejected"
    source = tmp_path / "staging.jsonl"
    source.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in (accepted, rejected)), encoding="utf-8")
    output = tmp_path / "accepted.jsonl"
    assert main([
        "dataset", "export", str(source), str(output),
        "--actor-id", "dataset_operator_01",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 0
    assert "exported 1" in capsys.readouterr().out
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_review_cli_persists_language_then_technical_approval(tmp_path: Path, capsys, access_files) -> None:
    record = pending(load("valid_single_tool.json"))
    source = tmp_path / "pending.json"
    language_output = tmp_path / "language.jsonl"
    technical_output = tmp_path / "technical.jsonl"
    source.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    common = ["--policy", access_files["policy"], "--audit-log", access_files["audit"]]

    assert main([
        "dataset", "review", str(source), str(language_output),
        "--record-id", record["id"], "--reviewer-id", "rev_language_01",
        "--role", "language", "--decision", "approve", *common,
    ]) == 0
    assert "record_status=needs_revision" in capsys.readouterr().out
    assert main([
        "dataset", "review", str(language_output), str(technical_output),
        "--record-id", record["id"], "--reviewer-id", "rev_technical_01",
        "--role", "technical", "--decision", "approve", *common,
    ]) == 0
    assert "record_status=accepted" in capsys.readouterr().out
    reviewed = json.loads(technical_output.read_text(encoding="utf-8"))
    assert [event["decision"] for event in reviewed["metadata"]["review"]["history"]] == [
        "approve", "approve",
    ]
