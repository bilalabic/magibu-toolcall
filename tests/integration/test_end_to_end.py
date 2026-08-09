from __future__ import annotations

import json
from pathlib import Path

from tool_call_tr.blueprints import BenchmarkCandidateConverter, BlueprintStore
from tool_call_tr.evaluation import BenchmarkEvaluator
from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
)
from tool_call_tr.generation import MockSemanticJudge
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.review import export_accepted
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_deterministic_infrastructure_flow(tmp_path: Path) -> None:
    # Demonstration registry -> validated scenario blueprint.
    registry = ToolRegistry.load(ROOT / "registry" / "registry.jsonl")
    validator = RuleBasedValidator(registry=registry)
    blueprints = BlueprintStore.load_directory(
        ROOT / "tests" / "fixtures" / "blueprints" / "valid", validator
    )
    blueprint = blueprints.get("bp_single_tool_001")

    # Blueprint -> review-required benchmark candidate. Gold remains isolated.
    candidate = BenchmarkCandidateConverter(registry).convert(
        blueprint,
        record_id="bench_ot_000020",
        user_message="On iki ile sekizi toplar mısın?",
    )
    assert candidate["metadata"]["review"]["status"] == "needs_revision"

    # Local deterministic execution -> normalized result.
    expected_call = candidate["expected"]["tool_calls"][0]["function"]
    result = ExecutionEngine(registry, ExecutionRouter([LocalExecutableAdapter()])).execute(
        ExecutionRequest(
            "call_001", expected_call["name"], expected_call["arguments"],
            ExecutionType.LOCAL_EXECUTABLE,
        )
    )
    assert result.status == ExecutionStatus.PASSED
    assert result.data == blueprint["expected_tool_result"] == {"result": 20}

    # Record verification metadata, then mark the PR-approved fixture accepted.
    candidate["metadata"]["execution"] = {"type": "local_executable", "status": "passed"}
    for stage in candidate["metadata"]["validation"]:
        candidate["metadata"]["validation"][stage] = "passed"
    candidate["metadata"]["validation"]["turn_level"] = "not_applicable"
    candidate["metadata"]["review"] = {
        "status": "accepted",
        "notes": "Approved through the protected GitHub pull request workflow.",
    }
    assert validator.validate_record("benchmark", candidate).valid

    # Evaluation is separate from gold, and export includes only accepted records.
    prediction = {
        "decision": "tool_call",
        "tool_calls": candidate["expected"]["tool_calls"],
        "response": None,
        "execution_status": result.status.value,
    }
    evaluation = BenchmarkEvaluator(registry, MockSemanticJudge()).evaluate(candidate, prediction)
    assert evaluation.exact_success == 1
    export_path = tmp_path / "accepted_benchmark.jsonl"
    assert export_accepted([candidate], export_path, validator=validator, kind="benchmark") == 1
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["id"] == candidate["id"]
    assert exported["expected"] == candidate["expected"]
