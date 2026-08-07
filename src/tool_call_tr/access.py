"""File-backed principals, lifecycle-scoped permissions, and hash-chained audit logs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tool_call_tr.schemas import SchemaStore


class AccessPolicyError(ValueError):
    pass


class AccessDenied(PermissionError):
    pass


class AccessPolicy:
    def __init__(self, value: dict[str, Any]) -> None:
        SchemaStore().validate("access", value)
        self.value = value
        self.principals: dict[str, dict[str, Any]] = {}
        for principal in value["principals"]:
            principal_id = principal["id"]
            if principal_id in self.principals:
                raise AccessPolicyError(f"duplicate principal ID: {principal_id}")
            teams = set(principal["teams"])
            if value["benchmark_dataset_team_exclusive"] and {"dataset", "benchmark"} <= teams:
                raise AccessPolicyError(f"principal belongs to both isolated teams: {principal_id}")
            self.principals[principal_id] = principal

    @classmethod
    def load(cls, path: Path) -> "AccessPolicy":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AccessPolicyError(f"cannot read access policy: {path}") from exc
        try:
            return cls(value)
        except AccessPolicyError:
            raise
        except Exception as exc:
            raise AccessPolicyError(f"invalid access policy: {path}") from exc

    def authorize(
        self,
        actor_id: str,
        *,
        lifecycle: str,
        permission: str,
        reviewer_role: str | None = None,
    ) -> dict[str, Any]:
        try:
            principal = self.principals[actor_id]
        except KeyError as exc:
            raise AccessDenied(f"unknown principal: {actor_id}") from exc
        if not principal["active"]:
            raise AccessDenied(f"inactive principal: {actor_id}")
        teams = set(principal["teams"])
        if lifecycle not in teams and "platform" not in teams:
            raise AccessDenied(f"principal {actor_id} has no {lifecycle} scope")
        if permission not in principal["permissions"]:
            raise AccessDenied(f"principal {actor_id} lacks {permission} permission")
        if reviewer_role is not None:
            expected_role = {"language": "language_reviewer", "technical": "technical_reviewer"}.get(reviewer_role)
            if expected_role is None:
                raise AccessDenied(f"unsupported reviewer role: {reviewer_role}")
            if expected_role not in principal["roles"]:
                raise AccessDenied(f"principal {actor_id} lacks {expected_role} role")
        return principal


def append_audit_event(
    path: Path,
    *,
    actor_id: str,
    lifecycle: str,
    action: str,
    resource_id: str,
    decision: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if decision not in {"allowed", "denied"}:
        raise ValueError("audit decision must be allowed or denied")
    previous = _last_audit_hash(path)
    event = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "lifecycle": lifecycle,
        "action": action,
        "resource_id": resource_id,
        "decision": decision,
        "previous_sha256": previous,
    }
    event["event_sha256"] = _event_hash(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def verify_audit_log(path: Path) -> dict[str, Any]:
    previous: str | None = None
    events = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AccessPolicyError(f"cannot read audit log: {path}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"valid": False, "events": events, "line": line_number, "error": "invalid_json"}
        event_hash = event.pop("event_sha256", None)
        if event.get("previous_sha256") != previous or event_hash != _event_hash(event):
            return {"valid": False, "events": events, "line": line_number, "error": "hash_chain_mismatch"}
        previous = event_hash
        events += 1
    return {"valid": True, "events": events, "last_sha256": previous}


def _last_audit_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    verification = verify_audit_log(path)
    if not verification["valid"]:
        raise AccessPolicyError("existing audit log failed hash-chain verification")
    return verification["last_sha256"]


def _event_hash(event: dict[str, Any]) -> str:
    value = {key: item for key, item in event.items() if key != "event_sha256"}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
