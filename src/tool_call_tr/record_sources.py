"""Deterministic discovery and hashing for JSON/JSONL record sources."""

from __future__ import annotations

import hashlib
from pathlib import Path


RECORD_SUFFIXES = frozenset({".json", ".jsonl"})


class UnsupportedRecordFormatError(ValueError):
    pass


def discover_record_files(path: Path) -> list[Path]:
    """Return one file or the supported top-level files in a directory."""

    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_dir():
        raise OSError(f"record source is neither a file nor a directory: {path}")
    return sorted(
        (
            candidate
            for candidate in path.iterdir()
            if candidate.is_file() and candidate.suffix.lower() in RECORD_SUFFIXES
        ),
        key=lambda candidate: (candidate.name.casefold(), candidate.name),
    )


def discover_jsonl_record_files(path: Path) -> list[Path]:
    """Return JSONL sources and reject JSON where a catalog requires JSONL."""

    files = discover_record_files(path)
    unsupported = [file_path for file_path in files if file_path.suffix.lower() != ".jsonl"]
    if unsupported:
        names = ", ".join(file_path.name for file_path in unsupported)
        raise UnsupportedRecordFormatError(f"only JSONL record files are allowed: {names}")
    if path.is_dir():
        shared_names = [file_path.name for file_path in files if file_path.name.casefold() == "registry.jsonl"]
        if shared_names:
            raise UnsupportedRecordFormatError(
                "shared registry.jsonl is not allowed in a fragment directory; "
                "use a descriptive <domain>_<source>.jsonl name"
            )
    return files


def file_sha256(path: Path) -> str:
    """Hash one file without loading it completely into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_source_sha256(path: Path) -> str:
    """Hash a record file or a directory's ordered file names and contents."""

    files = discover_jsonl_record_files(path)
    if not files:
        raise ValueError(f"record source directory contains no JSONL files: {path}")
    if path.is_file():
        return file_sha256(path)

    digest = hashlib.sha256()
    for file_path in files:
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(file_sha256(file_path)))
    return digest.hexdigest()
