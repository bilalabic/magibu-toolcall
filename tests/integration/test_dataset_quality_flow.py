from __future__ import annotations

import json
from pathlib import Path

from tool_call_tr.cli import main


ROOT = Path(__file__).resolve().parents[2]


def test_dataset_draft_quality_two_reviews_and_export(tmp_path: Path, capsys, access_files) -> None:
    record = json.loads(
        (ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json").read_text(encoding="utf-8")
    )
    record["metadata"]["execution"] = {"type": "local_executable", "status": "not_called"}
    record["metadata"]["validation"].update(
        {"execution": "not_run", "semantic": "not_run", "language": "not_run", "duplicate": "not_run"}
    )
    record["metadata"]["review"] = {
        "status": "needs_revision",
        "reviewer_ids": [],
        "notes": None,
        "contributor_id": "dataset_operator_01",
        "requires_two_reviewers": True,
        "history": [],
    }
    draft = tmp_path / "draft.json"
    checked = tmp_path / "checked.jsonl"
    quality_report = tmp_path / "quality.json"
    language_reviewed = tmp_path / "language.jsonl"
    fully_reviewed = tmp_path / "technical.jsonl"
    accepted = tmp_path / "accepted.jsonl"
    draft.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    operator = [
        "--actor-id", "dataset_operator_01", "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]
    review_access = ["--policy", access_files["policy"], "--audit-log", access_files["audit"]]

    assert main([
        "dataset", "quality", str(draft), str(checked),
        "--report", str(quality_report), *operator,
    ]) == 0
    capsys.readouterr()
    assert main([
        "dataset", "review", str(checked), str(language_reviewed),
        "--record-id", record["id"], "--reviewer-id", "rev_language_01",
        "--role", "language", "--decision", "approve", *review_access,
    ]) == 0
    assert "record_status=needs_revision" in capsys.readouterr().out
    assert main([
        "dataset", "review", str(language_reviewed), str(fully_reviewed),
        "--record-id", record["id"], "--reviewer-id", "rev_technical_01",
        "--role", "technical", "--decision", "approve", *review_access,
    ]) == 0
    assert "record_status=accepted" in capsys.readouterr().out
    assert main([
        "dataset", "export", str(fully_reviewed), str(accepted), *operator,
    ]) == 0
    assert "exported 1" in capsys.readouterr().out
    exported = json.loads(accepted.read_text(encoding="utf-8"))
    assert exported["metadata"]["validation"]["execution"] == "passed"
    assert exported["metadata"]["validation"]["language"] == "passed"
    assert exported["metadata"]["review"]["status"] == "accepted"
