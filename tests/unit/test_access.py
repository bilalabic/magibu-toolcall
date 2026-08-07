from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.access import AccessDenied, AccessPolicy, AccessPolicyError, append_audit_event, verify_audit_log
from tool_call_tr.cli import main


def policy_value() -> dict:
    return {
        "policy_version": "0.1.0",
        "benchmark_dataset_team_exclusive": True,
        "principals": [
            {
                "id": "rev_language_01", "active": True, "teams": ["dataset"],
                "roles": ["language_reviewer"], "permissions": ["review", "accept"],
            },
            {
                "id": "benchmark_lead_01", "active": True, "teams": ["benchmark"],
                "roles": ["technical_reviewer", "benchmark_lead"],
                "permissions": ["review", "accept", "export", "freeze", "benchmark_run"],
            },
            {
                "id": "disabled_01", "active": False, "teams": ["dataset"],
                "roles": ["contributor"], "permissions": ["generate", "quality_check"],
            },
        ],
    }


def test_policy_enforces_active_scope_permission_and_reviewer_role() -> None:
    policy = AccessPolicy(policy_value())
    assert policy.authorize("rev_language_01", lifecycle="dataset", permission="accept", reviewer_role="language")
    with pytest.raises(AccessDenied, match="no benchmark scope"):
        policy.authorize("rev_language_01", lifecycle="benchmark", permission="accept", reviewer_role="language")
    with pytest.raises(AccessDenied, match="technical_reviewer"):
        policy.authorize("rev_language_01", lifecycle="dataset", permission="review", reviewer_role="technical")
    with pytest.raises(AccessDenied, match="inactive"):
        policy.authorize("disabled_01", lifecycle="dataset", permission="generate")


def test_policy_blocks_dual_dataset_benchmark_membership() -> None:
    value = policy_value()
    value["principals"][0]["teams"] = ["dataset", "benchmark"]
    with pytest.raises(AccessPolicyError, match="both isolated teams"):
        AccessPolicy(value)


def test_hash_chained_audit_log_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    first = append_audit_event(
        path, actor_id="rev_language_01", lifecycle="dataset", action="accept",
        resource_id="tctr_ot_000001", decision="allowed", timestamp="2026-08-06T00:00:00+00:00",
    )
    second = append_audit_event(
        path, actor_id="benchmark_lead_01", lifecycle="benchmark", action="freeze",
        resource_id="freeze-001", decision="allowed", timestamp="2026-08-06T01:00:00+00:00",
    )
    assert second["previous_sha256"] == first["event_sha256"]
    assert verify_audit_log(path) == {"valid": True, "events": 2, "last_sha256": second["event_sha256"]}
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["decision"] = "denied"
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not verify_audit_log(path)["valid"]


def test_access_cli_validates_and_checks_scope(tmp_path: Path, capsys) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy_value()), encoding="utf-8")
    assert main(["access", "validate", str(path)]) == 0
    assert "principals=3" in capsys.readouterr().out
    assert main([
        "access", "check", str(path), "--actor-id", "rev_language_01",
        "--lifecycle", "dataset", "--permission", "accept", "--reviewer-role", "language",
    ]) == 0
    capsys.readouterr()
    assert main([
        "access", "check", str(path), "--actor-id", "rev_language_01",
        "--lifecycle", "benchmark", "--permission", "accept", "--reviewer-role", "language",
    ]) == 1
    assert "no benchmark scope" in capsys.readouterr().out
