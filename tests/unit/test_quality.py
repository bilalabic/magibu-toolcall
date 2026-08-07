from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time

import pytest

from tool_call_tr.cli import main
from tool_call_tr.generation.providers import ModelIdentity, ProviderResponse
from tool_call_tr.quality import QualityError, run_dataset_quality
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "dataset" / name).read_text(encoding="utf-8"))


def draft(name: str) -> dict:
    record = load(name)
    record["metadata"]["review"] = {
        "status": "needs_revision",
        "reviewer_ids": [],
        "notes": None,
        "contributor_id": "dataset_operator_01",
        "requires_two_reviewers": record["metadata"]["review"].get("requires_two_reviewers", False),
        "history": [],
    }
    call_count = sum(len(message.get("tool_calls", [])) for message in record["messages"])
    record["metadata"]["execution"] = (
        {"type": record["metadata"]["execution"]["type"], "status": "not_called"}
        if call_count
        else {"type": "not_applicable", "status": "not_called"}
    )
    for gate in ("execution", "semantic", "language", "duplicate"):
        record["metadata"]["validation"][gate] = "not_run" if gate != "execution" or call_count else "not_applicable"
    return record


def registry() -> ToolRegistry:
    return ToolRegistry.load(ROOT / "registry" / "registry.jsonl")


def test_quality_keeps_human_language_review_pending_for_no_tool_record() -> None:
    result = run_dataset_quality(
        [draft("valid_no_tool.json")],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        timestamp="2026-08-07T00:00:00+00:00",
    )
    record = result.records[0]
    assert result.passed
    assert record["metadata"]["execution"] == {"type": "not_applicable", "status": "not_called"}
    assert record["metadata"]["validation"]["semantic"] == "not_run"
    assert record["metadata"]["validation"]["duplicate"] == "passed"
    assert record["metadata"]["validation"]["language"] == "not_run"
    assert record["metadata"]["review"]["status"] == "needs_revision"


def test_quality_executes_local_call_and_compares_recorded_result() -> None:
    result = run_dataset_quality(
        [draft("valid_single_tool.json")],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
    )
    record = result.records[0]
    assert result.passed
    assert record["metadata"]["execution"]["status"] == "passed"
    assert record["metadata"]["validation"]["execution"] == "passed"
    assert result.report["records"][0]["execution_evidence"][0]["status"] == "passed"


def test_quality_fails_execution_when_recorded_result_differs() -> None:
    record = draft("valid_single_tool.json")
    record["messages"][2]["content"] = json.dumps({"result": 999})
    result = run_dataset_quality(
        [record],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
    )
    assert not result.passed
    assert result.records[0]["metadata"]["execution"]["status"] == "invalid_result"
    assert result.records[0]["metadata"]["validation"]["execution"] == "failed"


def test_quality_blocks_exact_duplicate_against_reference() -> None:
    candidate = draft("valid_no_tool.json")
    reference = copy.deepcopy(load("valid_no_tool.json"))
    reference["id"] = "tctr_ot_000010"
    result = run_dataset_quality(
        [candidate],
        references=[reference],
        registry=registry(),
        actor_id="dataset_operator_01",
    )
    assert not result.passed
    assert result.records[0]["metadata"]["validation"]["duplicate"] == "failed"
    assert result.report["duplicate_pairs"][0]["decision"] == "duplicate"


def test_quality_blocks_id_collision_with_reference() -> None:
    candidate = draft("valid_no_tool.json")
    with pytest.raises(QualityError, match="already exist"):
        run_dataset_quality(
            [candidate],
            references=[load("valid_no_tool.json")],
            registry=registry(),
            actor_id="dataset_operator_01",
        )


def test_quality_reference_corpus_must_be_accepted() -> None:
    reference = draft("valid_missing_parameter.json")
    with pytest.raises(QualityError, match="accepted records only"):
        run_dataset_quality(
            [draft("valid_no_tool.json")],
            references=[reference],
            registry=registry(),
            actor_id="dataset_operator_01",
        )


class HighSimilarity:
    def score(self, left: str, right: str) -> float:
        return 0.95


class LowSimilarity:
    def score(self, left: str, right: str) -> float:
        return 0.1


class BatchSimilarity:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def vectors(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [
            [1.0 if left == right else 0.0 for right in range(len(texts))]
            for left in range(len(texts))
        ]

    def score(self, left: str, right: str) -> float:
        raise AssertionError("batched quality scan must not call pairwise score")


def test_production_semantic_possible_duplicate_fails_duplicate_gate() -> None:
    candidate = draft("valid_no_tool.json")
    reference = load("valid_missing_parameter.json")
    result = run_dataset_quality(
        [candidate],
        references=[reference],
        registry=registry(),
        actor_id="dataset_operator_01",
        semantic=HighSimilarity(),
        semantic_provider="openai-test-transport",
        production_semantic=True,
        semantic_threshold=0.9,
    )
    validation = result.records[0]["metadata"]["validation"]
    assert not result.passed
    assert validation["semantic"] == "not_run"
    assert validation["duplicate"] == "failed"


def test_nonproduction_semantic_double_cannot_certify_gate() -> None:
    result = run_dataset_quality(
        [draft("valid_no_tool.json")],
        references=[load("valid_missing_parameter.json")],
        registry=registry(),
        actor_id="dataset_operator_01",
        semantic=LowSimilarity(),
        semantic_provider="token-test-double",
        production_semantic=False,
    )
    assert result.records[0]["metadata"]["validation"]["duplicate"] == "not_run"
    assert result.records[0]["metadata"]["validation"]["semantic"] == "not_run"


def test_quality_batches_unique_embeddings_and_retains_only_findings() -> None:
    records = []
    for number, query in enumerate(("Birinci özgün soru", "İkinci özgün soru", "Üçüncü özgün soru"), 1):
        record = draft("valid_no_tool.json")
        record["id"] = f"tctr_ot_{number:06d}"
        record["messages"][0]["content"] = query
        records.append(record)
    semantic = BatchSimilarity()
    result = run_dataset_quality(
        records,
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        semantic=semantic,
        semantic_provider="openai-test-transport",
        production_semantic=True,
    )
    assert len(semantic.calls) == 1
    assert len(semantic.calls[0]) == 3
    assert result.report["duplicate_scan"] == {
        "pairs_checked": 3,
        "semantic_comparisons": 3,
        "findings_retained": 0,
    }
    assert result.report["duplicate_pairs"] == []
    assert all(record["metadata"]["validation"]["duplicate"] == "passed" for record in result.records)


def judgment(verdict: str = "pass", score: int = 5) -> dict:
    return {
        "verdict": verdict,
        "scores": {
            name: score
            for name in (
                "language_naturalness", "tool_necessity", "tool_selection",
                "argument_grounding", "clarification_behavior", "result_grounding",
                "turkey_context",
            )
        },
        "issues": [],
        "summary": "Kalite değerlendirmesi tamamlandı.",
    }


class FakeJudge:
    def __init__(self, model: str, value: dict) -> None:
        self.model = model
        self.value = value
        self.calls = 0

    def judge_record(self, record: dict) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            self.value,
            ModelIdentity("openai", self.model, self.model, "dataset_quality_judge"),
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            request_id=f"req-{self.calls}",
        )


def test_production_judge_certifies_semantic_gate_and_records_usage() -> None:
    judge = FakeJudge("gpt-test-primary", judgment())
    result = run_dataset_quality(
        [draft("valid_no_tool.json")],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        judge=judge,
        judge_provider="openai",
        production_judge=True,
        judge_token_budget=10000,
    )
    assert result.records[0]["metadata"]["validation"]["semantic"] == "passed"
    assert result.report["judge"]["primary_tokens_used"] == 120
    assert result.report["records"][0]["judge_evidence"]["primary"]["request_id"] == "req-1"


def test_escalation_disagreement_blocks_semantic_gate() -> None:
    primary = FakeJudge("gpt-test-primary", judgment())
    escalation = FakeJudge("gpt-test-escalation", judgment("fail", 2))
    result = run_dataset_quality(
        [draft("valid_no_tool.json")],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        judge=primary,
        judge_provider="openai",
        production_judge=True,
        escalation_judge=escalation,
        escalation_sample_rate=1.0,
    )
    assert not result.passed
    assert result.records[0]["metadata"]["validation"]["semantic"] == "failed"
    assert result.report["records"][0]["judge_evidence"]["agreement"] is False


def test_judge_budget_exhaustion_blocks_without_api_call() -> None:
    judge = FakeJudge("gpt-test-primary", judgment())
    result = run_dataset_quality(
        [draft("valid_single_tool.json")],
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        judge=judge,
        judge_provider="openai",
        production_judge=True,
        judge_token_budget=1,
    )
    assert judge.calls == 0
    assert result.records[0]["metadata"]["validation"]["semantic"] == "failed"
    assert result.report["records"][0]["judge_evidence"]["primary"]["status"] == "token_budget_exhausted"


def test_quality_judge_uses_bounded_parallel_workers() -> None:
    records = []
    for number in range(1, 5):
        record = draft("valid_no_tool.json")
        record["id"] = f"tctr_ot_{number:06d}"
        record["messages"][0]["content"] = f"Özgün soru {number}"
        records.append(record)

    class ConcurrentJudge(FakeJudge):
        def __init__(self) -> None:
            super().__init__("gpt-test-primary", judgment())
            self.lock = threading.Lock()
            self.active = 0
            self.maximum_active = 0

        def judge_record(self, record: dict) -> ProviderResponse:
            with self.lock:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            time.sleep(0.02)
            response = super().judge_record(record)
            with self.lock:
                self.active -= 1
            return response

    judge = ConcurrentJudge()
    result = run_dataset_quality(
        records,
        references=[],
        registry=registry(),
        actor_id="dataset_operator_01",
        judge=judge,
        judge_provider="openai",
        production_judge=True,
        judge_max_workers=2,
        judge_token_budget=100000,
    )
    assert judge.maximum_active == 2
    assert result.report["judge"]["max_workers"] == 2
    assert result.report["judge"]["primary_tokens_used"] == 480
    assert all(record["metadata"]["validation"]["semantic"] == "passed" for record in result.records)


def test_quality_cli_writes_verified_draft_report_and_audit(tmp_path: Path, capsys, access_files) -> None:
    source = tmp_path / "draft.json"
    source.write_text(json.dumps(draft("valid_single_tool.json"), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "checked.jsonl"
    report = tmp_path / "quality.json"
    assert main([
        "dataset", "quality", str(source), str(output),
        "--report", str(report),
        "--actor-id", "dataset_operator_01",
        "--policy", access_files["policy"],
        "--audit-log", access_files["audit"],
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["records_checked"] == 1
    assert output.exists() and report.exists()
    checked = json.loads(output.read_text(encoding="utf-8"))
    assert checked["metadata"]["validation"]["execution"] == "passed"
    assert checked["metadata"]["validation"]["language"] == "not_run"
