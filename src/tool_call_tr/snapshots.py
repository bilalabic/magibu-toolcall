"""Provenance validation for versioned local snapshots of official sources.

A snapshot directory holds the raw files exactly as published, the data file
derived from them, and a ``provenance.json`` that declares both. Every declared
``sha256`` is re-computed here, so a provenance file cannot drift away from the
bytes it describes.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from tool_call_tr.config import Settings
from tool_call_tr.record_sources import file_sha256
from tool_call_tr.schemas import json_path


PROVENANCE_FILENAME = "provenance.json"
SCHEMA_FILENAME = "snapshot_provenance.schema.json"


class SnapshotError(ValueError):
    """A snapshot problem carrying a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the snapshot provenance schema; the schema file is authoritative."""

    path = schema_path or Settings.from_env().schemas_dir / SCHEMA_FILENAME
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError("SNAPSHOT_SCHEMA_UNAVAILABLE", f"cannot read {path}: {exc}") from exc
    Draft202012Validator.check_schema(schema)
    return schema


def discover_provenance_files(path: Path) -> list[Path]:
    """Return one provenance file or every provenance file under a directory."""

    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob(PROVENANCE_FILENAME), key=lambda found: found.as_posix())
    raise SnapshotError("SNAPSHOT_UNREADABLE", f"path does not exist: {path}")


def check_snapshot(provenance_path: Path, schema: dict[str, Any]) -> list[SnapshotError]:
    """Return every problem found in one snapshot, or an empty list when sound."""

    try:
        document = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [SnapshotError("SNAPSHOT_UNREADABLE", f"{provenance_path}: {exc}")]

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if schema_errors:
        return [
            SnapshotError(
                "SNAPSHOT_SCHEMA_INVALID",
                f"{provenance_path} {json_path(error)}: {error.message}",
            )
            for error in schema_errors
        ]

    issues: list[SnapshotError] = []
    declared = [entry["raw_file"] for entry in document["sources"]]
    duplicates = sorted({name for name in declared if declared.count(name) > 1})
    if duplicates:
        issues.append(
            SnapshotError(
                "SNAPSHOT_SCHEMA_INVALID",
                f"{provenance_path}: raw_file declared more than once: " + ", ".join(duplicates),
            )
        )
    for entry in document["sources"]:
        issues.extend(_check_file(provenance_path, entry["raw_file"], entry["sha256"]))
    issues.extend(_check_file(provenance_path, document["data_file"], None))
    return issues


def validate_path(path: Path, *, schema_path: Path | None = None) -> tuple[int, list[SnapshotError]]:
    """Validate one provenance file or a snapshot tree; report checked count and issues."""

    schema = load_schema(schema_path)
    files = discover_provenance_files(path)
    return len(files), [issue for file_path in files for issue in check_snapshot(file_path, schema)]


def _check_file(
    provenance_path: Path,
    relative: str,
    expected_sha256: str | None,
) -> list[SnapshotError]:
    """Resolve a declared path inside the snapshot and verify it byte for byte."""

    if any(part == ".." for part in PurePosixPath(relative).parts):
        return [
            SnapshotError(
                "SNAPSHOT_PATH_INVALID",
                f"{provenance_path}: declared path escapes the snapshot: {relative}",
            )
        ]
    target = provenance_path.parent / PurePosixPath(relative)
    if not target.is_file():
        return [
            SnapshotError(
                "SNAPSHOT_FILE_MISSING",
                f"{provenance_path}: declared file is not in the snapshot: {relative}",
            )
        ]
    if expected_sha256 is None:
        return []
    actual = file_sha256(target)
    if actual != expected_sha256:
        return [
            SnapshotError(
                "SNAPSHOT_HASH_MISMATCH",
                f"{provenance_path}: {relative} declares sha256={expected_sha256} but is {actual}",
            )
        ]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tool_call_tr.snapshots",
        description="Validate versioned source snapshots against their provenance declarations.",
    )
    parser.add_argument("path", type=Path, help="A provenance.json file or a directory to search.")
    parser.add_argument("--schema", type=Path, default=None, help="Override the schema path.")
    args = parser.parse_args(argv)

    try:
        checked, issues = validate_path(args.path, schema_path=args.schema)
    except SnapshotError as exc:
        print(f"ERROR {exc.code}: {exc.message}")
        return 1
    for issue in issues:
        print(f"ERROR {issue.code}: {issue.message}")
    if issues:
        return 1
    print(f"OK: {checked} snapshot(s) validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
