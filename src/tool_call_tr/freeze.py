"""Validated benchmark-gold freezing and checksum verification."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from tool_call_tr.contamination import ContaminationReport
from tool_call_tr.validation import RuleBasedValidator


SAFE_FREEZE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class FreezeError(ValueError):
    pass


def freeze_benchmark(
    records: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    manifest_path: Path,
    freeze_id: str,
    validator: RuleBasedValidator,
    contamination_report: ContaminationReport,
    dataset_sha256: str,
    frozen_at: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate and write immutable-by-manifest benchmark gold JSONL."""

    if not SAFE_FREEZE_ID.fullmatch(freeze_id):
        raise FreezeError("freeze_id must be a safe path-like identifier")
    if not contamination_report.passed:
        raise FreezeError(f"benchmark contamination gate did not pass: {contamination_report.status}")
    if not re.fullmatch(r"[0-9a-f]{64}", dataset_sha256):
        raise FreezeError("dataset_sha256 must be a lowercase SHA-256 digest")
    if output_path.resolve() == manifest_path.resolve():
        raise FreezeError("gold output and manifest paths must differ")
    existing = [path for path in (output_path, manifest_path) if path.exists()]
    if existing and not overwrite:
        raise FreezeError("output already exists: " + ", ".join(str(path) for path in existing))

    values = list(records)
    if not values:
        raise FreezeError("cannot freeze an empty benchmark")
    ids = [record.get("id") for record in values]
    duplicate_ids = sorted({record_id for record_id in ids if ids.count(record_id) > 1})
    if duplicate_ids:
        raise FreezeError("benchmark record IDs must be unique: " + ", ".join(map(str, duplicate_ids)))
    not_accepted = [record.get("id") for record in values if record.get("metadata", {}).get("review", {}).get("status") != "accepted"]
    if not_accepted:
        raise FreezeError("all frozen benchmark records must be accepted: " + ", ".join(map(str, not_accepted)))

    invalid = []
    for record in values:
        report = validator.validate_record("benchmark", record)
        if not report.valid:
            invalid.append(record.get("id"))
    if invalid:
        raise FreezeError("benchmark freeze blocked by validation failures: " + ", ".join(map(str, invalid)))

    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in values]
    content = ("\n".join(lines) + "\n").encode("utf-8")
    timestamp = frozen_at or datetime.now(timezone.utc).isoformat()
    _parse_timestamp(timestamp)
    manifest = {
        "manifest_version": "0.1.0",
        "artifact_type": "benchmark_gold",
        "freeze_id": freeze_id,
        "frozen_at": timestamp,
        "record_count": len(values),
        "record_ids": [record["id"] for record in values],
        "sha256": hashlib.sha256(content).hexdigest(),
        "schema_versions": sorted({record["schema_version"] for record in values}),
        "tool_registry_versions": sorted({record["tool_registry_version"] for record in values}),
        "contamination": {
            "status": contamination_report.status,
            "dataset_records": contamination_report.dataset_records,
            "benchmark_records": contamination_report.benchmark_records,
            "pairs_checked": contamination_report.pairs_checked,
            "dataset_sha256": dataset_sha256,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_benchmark_freeze(output_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify that frozen gold still matches its manifest exactly."""

    try:
        content = output_path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"cannot read frozen benchmark: {exc}") from exc
    try:
        lines = [line for line in content.decode("utf-8").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise FreezeError(f"frozen benchmark is not UTF-8: {exc}") from exc
    try:
        ids = [json.loads(line)["id"] for line in lines]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FreezeError(f"frozen benchmark is not valid JSONL: {exc}") from exc
    actual_hash = hashlib.sha256(content).hexdigest()
    checks = {
        "sha256": actual_hash == manifest.get("sha256"),
        "record_count": len(lines) == manifest.get("record_count"),
        "record_ids": ids == manifest.get("record_ids"),
    }
    return {
        "freeze_id": manifest.get("freeze_id"),
        "valid": all(checks.values()),
        "checks": checks,
        "actual_sha256": actual_hash,
        "expected_sha256": manifest.get("sha256"),
    }


def _parse_timestamp(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreezeError("frozen_at must be an ISO 8601 timestamp") from exc
