from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tool_call_tr.cli import main


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_dataset_and_benchmark_namespaces_generate_distinct_ids_and_validate(capsys) -> None:
    assert main(["dataset", "generate-id", "9", "--source-type", "translated"]) == 0
    assert capsys.readouterr().out.strip() == "tctr_tr_000009"
    assert main(["benchmark", "generate-id", "9", "--source-type", "translated"]) == 0
    assert capsys.readouterr().out.strip() == "bench_tr_000009"

    dataset = FIXTURES / "dataset" / "valid_single_tool.json"
    benchmark = FIXTURES / "benchmark" / "valid_tool_call.json"
    assert main(["dataset", "validate", str(dataset)]) == 0
    assert "OK:" in capsys.readouterr().out
    assert main(["benchmark", "validate", str(benchmark)]) == 0
    assert "OK:" in capsys.readouterr().out


def test_support_commands_are_namespaced_and_flat_legacy_commands_are_absent(capsys) -> None:
    assert main(["registry", "validate", str(ROOT / "registry" / "registry.jsonl")]) == 0
    assert "OK:" in capsys.readouterr().out
    assert main([
        "blueprint", "validate",
        str(FIXTURES / "blueprints" / "valid" / "single_tool.json"),
    ]) == 0
    assert "OK:" in capsys.readouterr().out
    assert main(["tool", "generate-call-id", "1"]) == 0
    assert capsys.readouterr().out.strip() == "call_001"
    with pytest.raises(SystemExit) as exit_info:
        main(["validate", "dataset", str(FIXTURES / "dataset" / "valid_single_tool.json")])
    assert exit_info.value.code == 2


def test_dataset_review_and_report_commands(tmp_path: Path, capsys, access_files) -> None:
    record = load(FIXTURES / "dataset" / "valid_no_tool.json")
    record["metadata"]["review"] = {
        "status": "needs_revision",
        "reviewer_ids": [],
        "notes": None,
        "contributor_id": "contrib_01",
        "requires_two_reviewers": False,
        "history": [],
    }
    source = tmp_path / "pending.json"
    reviewed = tmp_path / "reviewed.json"
    write_json(source, record)

    assert main([
        "dataset", "review", str(source), str(reviewed),
        "--record-id", record["id"],
        "--reviewer-id", "rev_language_01",
        "--role", "language",
        "--decision", "approve",
        "--timestamp", "2026-08-06T00:00:00+00:00",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 0
    capsys.readouterr()
    value = load(reviewed)
    assert value["metadata"]["review"]["status"] == "accepted"
    assert value["metadata"]["review"]["history"][0]["reviewer_role"] == "language"

    assert main(["dataset", "report", str(reviewed), "--output", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "dataset"
    assert report["records"] == 1
    assert report["review_statuses"] == {"accepted": 1}


def test_cross_corpus_contamination_isolated_from_within_corpus_dedupe(tmp_path: Path, capsys) -> None:
    dataset = load(FIXTURES / "dataset" / "valid_single_tool.json")
    benchmark = load(FIXTURES / "benchmark" / "valid_tool_call.json")
    benchmark["messages"][0]["content"] = dataset["messages"][0]["content"]
    dataset_path = tmp_path / "dataset.json"
    benchmark_path = tmp_path / "benchmark.json"
    write_json(dataset_path, dataset)
    write_json(benchmark_path, benchmark)

    assert main([
        "benchmark", "contamination-check",
        "--benchmark", str(benchmark_path),
        "--dataset", str(dataset_path),
        "--semantic-provider", "token-test-double",
        "--output", "json",
    ]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert report["blocking_count"] == 1
    assert report["findings"][0]["benchmark_id"] == benchmark["id"]


def test_dataset_quality_requires_live_confirmation_for_openai(tmp_path: Path, capsys) -> None:
    assert main([
        "dataset", "quality", str(tmp_path / "input.jsonl"), str(tmp_path / "output.jsonl"),
        "--semantic-provider", "openai",
        "--judge-provider", "openai",
        "--actor-id", "dataset_operator_01",
        "--policy", str(tmp_path / "policy.json"),
        "--audit-log", str(tmp_path / "audit.jsonl"),
    ]) == 1
    assert "--confirm-live is required" in capsys.readouterr().out


def test_benchmark_freeze_and_checksum_verification(tmp_path: Path, capsys, access_files) -> None:
    source = FIXTURES / "benchmark" / "valid_tool_call.json"
    dataset = FIXTURES / "dataset" / "valid_single_tool.json"
    gold = tmp_path / "gold.jsonl"
    manifest = tmp_path / "gold.manifest.json"
    assert main([
        "benchmark", "freeze", str(source), str(gold),
        "--dataset", str(dataset),
        "--manifest", str(manifest),
        "--freeze-id", "pilot-001",
        "--frozen-at", "2026-08-06T00:00:00+00:00",
        "--semantic-provider", "token-test-double",
        "--output", "json",
        "--actor-id", "benchmark_lead_01",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 0
    freeze = json.loads(capsys.readouterr().out)
    assert freeze["record_count"] == 1
    assert gold.exists() and manifest.exists()

    assert main(["benchmark", "verify-freeze", str(gold), str(manifest), "--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    gold.write_text(gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert main(["benchmark", "verify-freeze", str(gold), str(manifest), "--output", "json"]) == 1
    assert not json.loads(capsys.readouterr().out)["valid"]


def test_benchmark_freeze_cannot_skip_contamination_gate(tmp_path: Path, capsys, access_files) -> None:
    benchmark = load(FIXTURES / "benchmark" / "valid_tool_call.json")
    dataset = load(FIXTURES / "dataset" / "valid_single_tool.json")
    dataset["messages"][0]["content"] = benchmark["messages"][0]["content"]
    benchmark_path = tmp_path / "benchmark.json"
    dataset_path = tmp_path / "dataset.json"
    gold = tmp_path / "gold.jsonl"
    write_json(benchmark_path, benchmark)
    write_json(dataset_path, dataset)

    assert main([
        "benchmark", "freeze", str(benchmark_path), str(gold),
        "--dataset", str(dataset_path),
        "--freeze-id", "blocked-001",
        "--semantic-provider", "token-test-double",
        "--actor-id", "benchmark_lead_01",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 1
    assert "contamination gate did not pass" in capsys.readouterr().out
    assert not gold.exists()


def test_benchmark_run_writes_predictions_below_runs_and_reports(tmp_path: Path, capsys, access_files) -> None:
    gold_record = load(FIXTURES / "benchmark" / "valid_tool_call.json")
    gold_path = tmp_path / "gold.json"
    predictions_path = tmp_path / "predictions.jsonl"
    write_json(gold_path, gold_record)
    prediction = {
        "benchmark_id": gold_record["id"],
        "prediction": {
            "decision": "tool_call",
            "tool_calls": gold_record["expected"]["tool_calls"],
            "response": None,
            "execution_status": "passed",
        },
    }
    predictions_path.write_text(json.dumps(prediction, ensure_ascii=False) + "\n", encoding="utf-8")
    gold_before = gold_path.read_text(encoding="utf-8")

    assert main([
        "benchmark", "run", str(gold_path), str(predictions_path),
        "--model-name", "fixture-model",
        "--model-version", "1",
        "--run-id", "run-001",
        "--runs-dir", str(tmp_path / "runs"),
        "--semantic-judge-test-double",
        "--output", "json",
        "--actor-id", "benchmark_lead_01",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    run_log = Path(result["run_log"])
    assert run_log == tmp_path / "runs" / "fixture-model" / "run-001.jsonl"
    assert result["metrics"]["overall_exact_success"] == 1.0
    assert gold_path.read_text(encoding="utf-8") == gold_before

    assert main(["benchmark", "report", str(run_log), "--output", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["examples"] == 1
    assert report["overall_exact_success"] == 1.0
