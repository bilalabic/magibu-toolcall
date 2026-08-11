"""Resumable, checksum-bound shard jobs for dataset and benchmark operations."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from tool_call_tr.ids import generate_record_id
from tool_call_tr.record_sources import file_sha256, record_source_sha256
from tool_call_tr.schemas import SchemaStore
from tool_call_tr.sources import iter_source_rows


class BatchError(ValueError):
    pass


Processor = Callable[[dict[str, Any], int, str | None], dict[str, Any]]


def create_job_manifest(
    *,
    job_id: str,
    lifecycle: str,
    operation: str,
    input_path: Path,
    output_path: Path,
    checkpoint_path: Path,
    error_path: Path,
    shard_size: int,
    targets: dict[str, dict[str, int]] | None = None,
    source_type: str | None = None,
    start_number: int | None = None,
    existing_ids: Iterable[str] = (),
    registry_path: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if lifecycle not in {"dataset", "benchmark"}:
        raise BatchError(f"unsupported lifecycle: {lifecycle}")
    if shard_size < 1:
        raise BatchError("shard size must be positive")
    rows = iter_source_rows(input_path)
    total = 0
    observed: dict[str, dict[str, int]] = {dimension: {} for dimension in (targets or {})}
    for _, row in rows:
        total += 1
        for dimension in observed:
            metadata = row.get("metadata")
            value = metadata.get(dimension) if isinstance(metadata, dict) else None
            if not isinstance(value, str):
                raise BatchError(f"input row {total} has no metadata.{dimension} for its target plan")
            observed[dimension][value] = observed[dimension].get(value, 0) + 1
    if total < 1:
        raise BatchError("batch input cannot be empty")
    distributions = targets or {}
    for dimension, counts in distributions.items():
        if not isinstance(counts, dict) or any(not isinstance(value, int) or value < 0 for value in counts.values()):
            raise BatchError(f"target distribution {dimension} contains invalid counts")
        if sum(counts.values()) != total:
            raise BatchError(f"target distribution {dimension} totals {sum(counts.values())}, expected {total}")
        if dict(sorted(counts.items())) != dict(sorted(observed[dimension].items())):
            raise BatchError(f"input distribution {dimension} does not match the target plan")
    reserved_paths = [output_path, checkpoint_path, error_path, Path(str(checkpoint_path) + ".parts"), Path(str(checkpoint_path) + ".errors")]
    occupied = [str(path) for path in reserved_paths if path.exists()]
    if occupied:
        raise BatchError("new job paths already exist: " + ", ".join(occupied))
    id_plan = None
    if source_type is not None or start_number is not None:
        if source_type is None or start_number is None or start_number < 1:
            raise BatchError("source_type and positive start_number must be supplied together")
        planned_ids = [generate_record_id(lifecycle, source_type, start_number + index) for index in range(total)]
        collisions = sorted(set(planned_ids) & set(existing_ids))
        if collisions:
            raise BatchError("planned IDs collide with existing records: " + ", ".join(collisions[:10]))
        id_plan = {"source_type": source_type, "start_number": start_number, "end_number": start_number + total - 1}
    now = timestamp or datetime.now(timezone.utc).isoformat()
    shards = [
        {"index": index, "start": start, "end": min(start + shard_size, total), "status": "pending"}
        for index, start in enumerate(range(0, total, shard_size))
    ]
    manifest = {
        "job_version": "0.1.0",
        "job_id": job_id,
        "lifecycle": lifecycle,
        "operation": operation,
        "input_path": str(input_path.resolve()),
        "input_sha256": _file_hash(input_path),
        "output_path": str(output_path.resolve()),
        "error_path": str(error_path.resolve()),
        "checkpoint_path": str(checkpoint_path.resolve()),
        "total_items": total,
        "shard_size": shard_size,
        "shards": shards,
        "target_distributions": distributions,
        "id_plan": id_plan,
        "registry_binding": (
            {"path": str(registry_path.resolve()), "sha256": record_source_sha256(registry_path)}
            if registry_path is not None
            else None
        ),
        "status": "planned",
        "counts": {"processed": 0, "succeeded": 0, "failed": 0},
        "created_at": now,
        "updated_at": now,
    }
    SchemaStore().validate("job", manifest)
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any], *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise BatchError(f"manifest already exists: {path}")
    SchemaStore().validate("job", manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path, *, verify_input: bool = True) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError(f"cannot read job manifest: {path}") from exc
    try:
        SchemaStore().validate("job", manifest)
    except Exception as exc:
        raise BatchError(f"invalid job manifest: {path}") from exc
    if verify_input:
        input_path = Path(manifest["input_path"])
        if not input_path.exists() or _file_hash(input_path) != manifest["input_sha256"]:
            raise BatchError("job input is missing or its checksum changed")
        registry_binding = manifest["registry_binding"]
        if registry_binding is not None:
            registry_path = Path(registry_binding["path"])
            if not registry_path.exists() or record_source_sha256(registry_path) != registry_binding["sha256"]:
                raise BatchError("job registry is missing or its checksum changed")
    _validate_shards(manifest)
    return manifest


def run_job(
    manifest_path: Path,
    processor: Processor,
    *,
    timestamp: Callable[[], str] | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    if not 1 <= max_workers <= 32:
        raise BatchError("max_workers must be between 1 and 32")
    manifest = load_manifest(manifest_path)
    if manifest["status"] in {"completed", "completed_with_errors"}:
        raise BatchError("completed jobs are immutable; create a new job to rerun")
    output_path = Path(manifest["output_path"])
    error_path = Path(manifest["error_path"])
    checkpoint_path = Path(manifest["checkpoint_path"])
    parts_dir = Path(str(checkpoint_path) + ".parts")
    errors_dir = Path(str(checkpoint_path) + ".errors")
    parts_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = _load_checkpoint(checkpoint_path, manifest)
    if not checkpoint["processed"] and (output_path.exists() or error_path.exists()):
        raise BatchError("output/error path exists before the first checkpoint; refusing ambiguous resume")
    now = timestamp or (lambda: datetime.now(timezone.utc).isoformat())
    manifest["status"] = "running"
    manifest["updated_at"] = now()
    _replace_json(manifest_path, manifest)

    rows = iter(iter_source_rows(Path(manifest["input_path"])))
    for shard in manifest["shards"]:
        indexes = range(shard["start"], shard["end"])
        shard["status"] = "running"
        pending: list[tuple[int, dict[str, Any], str | None]] = []
        for index in indexes:
            try:
                _, row = next(rows)
            except StopIteration as exc:
                raise BatchError("job input ended before the planned item count") from exc
            if index in checkpoint["processed"]:
                continue
            pending.append((index, row, planned_record_id(manifest, index)))

        def persist(index: int, record_id: str | None, result: dict[str, Any] | None, exc: Exception | None) -> None:
            try:
                if exc is not None:
                    raise exc
                if not isinstance(result, dict):
                    raise BatchError("batch processor must return a JSON object")
                _write_part(parts_dir / f"{index:09d}.json", result)
                checkpoint["succeeded"].append(index)
            except Exception as exc:  # job boundary records item failures and continues
                failure = {
                    "index": index,
                    "record_id": record_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
                _write_part(errors_dir / f"{index:09d}.json", failure)
                checkpoint["failed"].append(index)
            checkpoint["processed"].append(index)
            checkpoint["processed"].sort()
            checkpoint["succeeded"].sort()
            checkpoint["failed"].sort()
            _replace_json(checkpoint_path, checkpoint)

        if max_workers == 1:
            for index, row, record_id in pending:
                try:
                    result = processor(row, index, record_id)
                except Exception as exc:  # job boundary records item failures and continues
                    persist(index, record_id, None, exc)
                else:
                    persist(index, record_id, result, None)
        elif pending:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="magibu-provider") as executor:
                futures: dict[Future[dict[str, Any]], tuple[int, str | None]] = {
                    executor.submit(processor, row, index, record_id): (index, record_id)
                    for index, row, record_id in pending
                }
                for future in as_completed(futures):
                    index, record_id = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # job boundary records item failures and continues
                        persist(index, record_id, None, exc)
                    else:
                        persist(index, record_id, result, None)
        shard_failed = any(index in checkpoint["failed"] for index in indexes)
        shard["status"] = "completed_with_errors" if shard_failed else "completed"
    try:
        next(rows)
    except StopIteration:
        pass
    else:
        raise BatchError("job input contains more rows than the planned item count")

    _assemble_jsonl(parts_dir, output_path)
    _assemble_jsonl(errors_dir, error_path)
    manifest["counts"] = {
        "processed": len(checkpoint["processed"]),
        "succeeded": len(checkpoint["succeeded"]),
        "failed": len(checkpoint["failed"]),
    }
    manifest["status"] = "completed_with_errors" if checkpoint["failed"] else "completed"
    manifest["updated_at"] = now()
    _replace_json(manifest_path, manifest)
    return manifest


def planned_record_id(manifest: dict[str, Any], index: int) -> str | None:
    plan = manifest.get("id_plan")
    if plan is None:
        return None
    return generate_record_id(manifest["lifecycle"], plan["source_type"], plan["start_number"] + index)


def collect_existing_ids(paths: Iterable[Path]) -> set[str]:
    ids: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for _, record in iter_source_rows(path):
            value = record.get("id")
            if isinstance(value, str):
                if value in ids:
                    raise BatchError(f"existing record ID occurs more than once: {value}")
                ids.add(value)
    return ids


def _load_checkpoint(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {"job_id": manifest["job_id"], "input_sha256": manifest["input_sha256"], "processed": [], "succeeded": [], "failed": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError("checkpoint cannot be read") from exc
    if value.get("job_id") != manifest["job_id"] or value.get("input_sha256") != manifest["input_sha256"]:
        raise BatchError("checkpoint does not belong to this job/input")
    for field in ("processed", "succeeded", "failed"):
        if not isinstance(value.get(field), list) or any(not isinstance(index, int) for index in value[field]):
            raise BatchError("checkpoint index lists are invalid")
    return value


def _validate_shards(manifest: dict[str, Any]) -> None:
    expected = 0
    for index, shard in enumerate(manifest["shards"]):
        if shard["index"] != index or shard["start"] != expected or shard["end"] <= shard["start"]:
            raise BatchError("job shards do not form a contiguous ordered range")
        expected = shard["end"]
    if expected != manifest["total_items"]:
        raise BatchError("job shards do not cover every input item")


def _write_part(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise BatchError(f"batch part already exists without a checkpoint: {path.name}")
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _assemble_jsonl(directory: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".assembling")
    with temporary.open("w", encoding="utf-8") as handle:
        for path in sorted(directory.glob("*.json")):
            value = path.read_text(encoding="utf-8").strip()
            if value:
                handle.write(value + "\n")
    if output_path.exists():
        if _file_hash(output_path) != _file_hash(temporary):
            temporary.unlink()
            raise BatchError(f"existing assembled output differs from job parts: {output_path}")
        temporary.unlink()
        return
    temporary.replace(output_path)


def _replace_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    return file_sha256(path)
