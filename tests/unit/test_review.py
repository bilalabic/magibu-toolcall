from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tool_call_tr.cli import build_parser, main
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.review import ReviewError, export_accepted
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "dataset" / name).read_text(encoding="utf-8"))


def validator() -> RuleBasedValidator:
    return RuleBasedValidator(registry=ToolRegistry.load(ROOT / "registry" / "registry.jsonl"))


def test_export_includes_only_pr_approved_records(tmp_path: Path) -> None:
    accepted = load("valid_no_tool.json")
    revision = copy.deepcopy(load("valid_missing_parameter.json"))
    revision["metadata"]["review"] = {"status": "needs_revision", "notes": None}
    rejected = copy.deepcopy(load("valid_single_tool.json"))
    rejected["metadata"]["review"] = {"status": "rejected", "notes": None}

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


def test_export_cli_needs_no_login_or_access_policy(tmp_path: Path, capsys) -> None:
    accepted = load("valid_no_tool.json")
    source = tmp_path / "pr-approved.jsonl"
    source.write_text(json.dumps(accepted, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "accepted.jsonl"

    assert main(["dataset", "export", str(source), str(output)]) == 0
    assert "exported 1" in capsys.readouterr().out


def test_reviewer_cli_command_is_removed() -> None:
    parser = build_parser()
    dataset_action = next(
        action for action in parser._actions if getattr(action, "choices", None) and "dataset" in action.choices
    )
    dataset_parser = dataset_action.choices["dataset"]
    command_action = next(action for action in dataset_parser._actions if getattr(action, "choices", None))
    assert "review" not in command_action.choices
