"""Write model outputs separately from immutable benchmark gold records."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def run_log_path(runs_dir: Path, model_name: str, run_id: str) -> Path:
    if not SAFE_SEGMENT.fullmatch(model_name) or not SAFE_SEGMENT.fullmatch(run_id):
        raise ValueError("model_name and run_id must be safe path segments")
    return runs_dir / model_name / f"{run_id}.jsonl"


def write_run_log(
    runs_dir: Path,
    model_name: str,
    run_id: str,
    outputs: Iterable[dict[str, Any]],
    *,
    model_version: str | None = None,
    overwrite: bool = False,
) -> Path:
    path = run_log_path(runs_dir, model_name, run_id)
    if path.exists() and not overwrite:
        raise ValueError(f"run log already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = []
    for output in outputs:
        lines.append(json.dumps({"model_name": model_name, "model_version": model_version, "run_id": run_id, "recorded_at": timestamp, **output}, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path
