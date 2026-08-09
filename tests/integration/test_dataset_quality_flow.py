from __future__ import annotations

import json
from pathlib import Path

from tool_call_tr.cli import main
from tool_call_tr.generation.providers import ModelIdentity, ProviderResponse


ROOT = Path(__file__).resolve().parents[2]


def test_dataset_draft_quality_pr_approval_and_export(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    record = json.loads(
        (ROOT / "tests" / "fixtures" / "dataset" / "valid_single_tool.json").read_text(encoding="utf-8")
    )
    record["metadata"]["execution"] = {"type": "local_executable", "status": "not_called"}
    record["metadata"]["validation"].update(
        {"execution": "not_run", "semantic": "not_run", "language": "not_run", "duplicate": "not_run"}
    )
    record["metadata"]["review"] = {
        "status": "needs_revision",
        "notes": None,
    }
    draft = tmp_path / "draft.json"
    checked = tmp_path / "checked.jsonl"
    quality_report = tmp_path / "quality.json"
    pr_approved = tmp_path / "pr-approved.jsonl"
    accepted = tmp_path / "accepted.jsonl"
    draft.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    class PassingJudge:
        model = "gpt-test-primary"

        def require_configured(self) -> None:
            return None

        def judge_record(self, candidate: dict) -> ProviderResponse:
            scores = {
                name: 5 for name in (
                    "language_naturalness", "tool_necessity", "tool_selection",
                    "argument_grounding", "clarification_behavior", "result_grounding",
                    "turkey_context",
                )
            }
            return ProviderResponse(
                {"verdict": "pass", "scores": scores, "issues": [], "summary": "Uygun."},
                ModelIdentity("openai", self.model, self.model, "dataset_quality_judge"),
                usage={"total_tokens": 100},
            )

    monkeypatch.setattr(
        "tool_call_tr.cli.OpenAIQualityJudge.from_settings",
        lambda settings, escalation=False: PassingJudge(),
    )

    assert main([
        "dataset", "quality", str(draft), str(checked),
        "--report", str(quality_report), "--judge-provider", "openai", "--confirm-live",
    ]) == 0
    capsys.readouterr()
    approved_record = json.loads(checked.read_text(encoding="utf-8"))
    approved_record["metadata"]["validation"]["language"] = "passed"
    approved_record["metadata"]["review"] = {
        "status": "accepted",
        "notes": "Approved through the protected GitHub pull request workflow.",
    }
    pr_approved.write_text(json.dumps(approved_record, ensure_ascii=False), encoding="utf-8")
    assert main(["dataset", "export", str(pr_approved), str(accepted)]) == 0
    assert "exported 1" in capsys.readouterr().out
    exported = json.loads(accepted.read_text(encoding="utf-8"))
    assert exported["metadata"]["validation"]["execution"] == "passed"
    assert exported["metadata"]["validation"]["language"] == "passed"
    assert exported["metadata"]["review"]["status"] == "accepted"
