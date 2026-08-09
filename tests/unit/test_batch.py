from __future__ import annotations

import json
from pathlib import Path
import threading
import time

import pytest

from tool_call_tr.cli import main
from tool_call_tr.generation.providers import ModelIdentity, ProviderResponse
from tool_call_tr.generation.providers import ProviderError
from tool_call_tr.batch import (
    BatchError,
    create_job_manifest,
    load_manifest,
    planned_record_id,
    run_job,
    write_manifest,
)


def write_rows(path: Path, count: int) -> None:
    path.write_text("".join(json.dumps({"value": index, "metadata": {"main_category": "single_tool"}}) + "\n" for index in range(count)), encoding="utf-8")


def manifest_for(tmp_path: Path, *, count: int = 5, existing_ids=()) -> tuple[Path, dict]:
    source = tmp_path / "input.jsonl"
    manifest_path = tmp_path / "job.json"
    write_rows(source, count)
    manifest = create_job_manifest(
        job_id="dataset-generation-001",
        lifecycle="dataset",
        operation="scenario_generation",
        input_path=source,
        output_path=tmp_path / "output.jsonl",
        checkpoint_path=tmp_path / "checkpoint.json",
        error_path=tmp_path / "errors.jsonl",
        shard_size=2,
        targets={"main_category": {"single_tool": count}},
        source_type="original_turkish",
        start_number=10,
        existing_ids=existing_ids,
        timestamp="2026-08-06T00:00:00+00:00",
    )
    write_manifest(manifest_path, manifest)
    return manifest_path, manifest


def test_manifest_plans_contiguous_shards_targets_and_ids(tmp_path: Path) -> None:
    manifest_path, manifest = manifest_for(tmp_path)
    assert [(shard["start"], shard["end"]) for shard in manifest["shards"]] == [(0, 2), (2, 4), (4, 5)]
    assert planned_record_id(manifest, 0) == "tctr_ot_000010"
    assert planned_record_id(manifest, 4) == "tctr_ot_000014"
    assert manifest["registry_binding"] is None
    assert load_manifest(manifest_path)["input_sha256"] == manifest["input_sha256"]


def test_manifest_rejects_changed_checksum_bound_registry(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    write_rows(source, 1)
    registry = tmp_path / "registry.jsonl"
    registry.write_text("original\n", encoding="utf-8")
    manifest_path = tmp_path / "job.json"
    manifest = create_job_manifest(
        job_id="dataset-generation-registry-001",
        lifecycle="dataset",
        operation="scenario_generation",
        input_path=source,
        output_path=tmp_path / "output.jsonl",
        checkpoint_path=tmp_path / "checkpoint.json",
        error_path=tmp_path / "errors.jsonl",
        shard_size=1,
        targets={"main_category": {"single_tool": 1}},
        source_type="original_turkish",
        start_number=1,
        registry_path=registry,
        timestamp="2026-08-07T00:00:00+00:00",
    )
    write_manifest(manifest_path, manifest)
    assert load_manifest(manifest_path)["registry_binding"]["path"] == str(registry.resolve())
    registry.write_text("changed\n", encoding="utf-8")
    with pytest.raises(BatchError, match="registry.*checksum"):
        load_manifest(manifest_path)


def test_manifest_rejects_distribution_and_id_collisions(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    write_rows(source, 2)
    base = {
        "job_id": "dataset-generation-001", "lifecycle": "dataset", "operation": "scenario_generation",
        "input_path": source, "output_path": tmp_path / "out.jsonl", "checkpoint_path": tmp_path / "checkpoint.json",
        "error_path": tmp_path / "errors.jsonl", "shard_size": 1, "source_type": "original_turkish", "start_number": 1,
    }
    with pytest.raises(BatchError, match="totals"):
        create_job_manifest(**base, targets={"main_category": {"single_tool": 1}})
    with pytest.raises(BatchError, match="collide"):
        create_job_manifest(**base, existing_ids={"tctr_ot_000002"})


def test_job_continues_item_failures_and_assembles_ordered_outputs(tmp_path: Path) -> None:
    manifest_path, _ = manifest_for(tmp_path)

    def processor(row, index, record_id):
        if index == 2:
            raise ValueError("invalid candidate")
        return {"id": record_id, "value": row["value"]}

    completed = run_job(manifest_path, processor, timestamp=lambda: "2026-08-06T01:00:00+00:00")
    assert completed["status"] == "completed_with_errors"
    assert completed["counts"] == {"processed": 5, "succeeded": 4, "failed": 1}
    output = [json.loads(line) for line in (tmp_path / "output.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["value"] for record in output] == [0, 1, 3, 4]
    errors = [json.loads(line) for line in (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert errors[0]["record_id"] == "tctr_ot_000012"
    with pytest.raises(BatchError, match="immutable"):
        run_job(manifest_path, processor)


def test_job_supports_bounded_parallel_processing_with_ordered_output(tmp_path: Path) -> None:
    manifest_path, _ = manifest_for(tmp_path, count=4)
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def processor(row, index, record_id):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return {"id": record_id, "value": row["value"]}

    completed = run_job(manifest_path, processor, max_workers=2)
    output = [json.loads(line) for line in (tmp_path / "output.jsonl").read_text(encoding="utf-8").splitlines()]
    assert completed["status"] == "completed"
    assert maximum_active == 2
    assert [record["value"] for record in output] == [0, 1, 2, 3]


def test_job_resumes_after_process_interruption_without_duplicate_parts(tmp_path: Path) -> None:
    manifest_path, _ = manifest_for(tmp_path, count=4)

    def interrupted(row, index, record_id):
        if index == 2:
            raise KeyboardInterrupt()
        return {"id": record_id, "value": row["value"]}

    with pytest.raises(KeyboardInterrupt):
        run_job(manifest_path, interrupted, timestamp=lambda: "2026-08-06T01:00:00+00:00")
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["processed"] == [0, 1]

    completed = run_job(
        manifest_path,
        lambda row, index, record_id: {"id": record_id, "value": row["value"]},
        timestamp=lambda: "2026-08-06T02:00:00+00:00",
    )
    assert completed["status"] == "completed"
    output = [json.loads(line) for line in (tmp_path / "output.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["value"] for record in output] == [0, 1, 2, 3]


def test_job_blocks_when_input_changes_after_plan(tmp_path: Path) -> None:
    manifest_path, manifest = manifest_for(tmp_path)
    Path(manifest["input_path"]).write_text("{\"changed\":true}\n", encoding="utf-8")
    with pytest.raises(BatchError, match="checksum"):
        load_manifest(manifest_path)


def test_batch_cli_plans_reports_and_runs_validated_candidate_job(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    blueprint = root / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json"
    manifest = tmp_path / "job.json"
    output = tmp_path / "candidates.jsonl"
    assert main([
        "dataset", "batch", "plan", str(blueprint), str(manifest),
        "--job-id", "dataset-generation-020",
        "--operation", "scenario_generation",
        "--output", str(output),
        "--checkpoint", str(tmp_path / "checkpoint.json"),
        "--errors", str(tmp_path / "errors.jsonl"),
        "--shard-size", "1",
        "--source-type", "original_turkish",
        "--start-number", "20",
        "--timestamp", "2026-08-06T00:00:00+00:00",
    ]) == 0
    capsys.readouterr()
    assert main(["dataset", "batch", "status", str(manifest), "--output", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["input_verified"]

    class FakeProvider:
        model = "fixture-model"

        def require_configured(self):
            return None

        def generate_language_plan(self, blueprint):
            return ProviderResponse(
                {
                    "user_messages": ["Merhaba"],
                    "intermediate_assistant_response": None,
                    "final_response": "Merhaba!",
                },
                ModelIdentity("fake", self.model, "1", "dataset_language_generator"),
            )

    monkeypatch.setattr("tool_call_tr.cli.DeepSeekIntegration.from_settings", lambda settings: FakeProvider())
    assert main(["dataset", "batch", "run", str(manifest), "--execute-live"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["provider_budget_accounted_tokens"] < 5000
    generated = json.loads(output.read_text(encoding="utf-8"))
    assert generated["id"] == "tctr_ot_000020"
    assert generated["metadata"]["review"]["status"] == "needs_revision"
    assert main(["dataset", "batch", "report", str(manifest), "--output", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["distribution_targets_met"]


def test_normal_dataset_generation_plans_paths_and_sanitizes_provider_quality_claims(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    blueprint = root / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json"
    output = tmp_path / "staging" / "pilot.jsonl"
    class FakeProvider:
        model = "fixture-model"

        def require_configured(self):
            return None

        def generate_language_plan(self, blueprint):
            return ProviderResponse(
                {
                    "user_messages": ["Merhaba"],
                    "intermediate_assistant_response": None,
                    "final_response": "Merhaba!",
                },
                ModelIdentity("fake", self.model, "2026-08-07", "dataset_language_generator"),
            )

    monkeypatch.setattr("tool_call_tr.cli.DeepSeekIntegration.from_settings", lambda settings: FakeProvider())
    monkeypatch.setattr("tool_call_tr.cli.dataset_record_paths", lambda project_root: [])
    assert main([
        "dataset", "generate", str(blueprint),
        "--job-id", "dataset-pilot-001",
        "--runs-dir", str(tmp_path / "runs"),
        "--output", str(output),
        "--timestamp", "2026-08-07T00:00:00+00:00",
        "--execute-live",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["job_id"] == "dataset-pilot-001"
    assert result["status"] == "completed"
    assert result["provider_budget_accounted_tokens"] < 5000
    assert Path(result["manifest"]).exists()
    assert result["output"] == str(output.resolve())

    generated = json.loads(output.read_text(encoding="utf-8"))
    assert generated["id"] == "tctr_ot_000001"
    assert generated["metadata"]["review"]["status"] == "needs_revision"
    assert generated["metadata"]["validation"]["language"] == "not_run"
    assert generated["metadata"]["validation"]["duplicate"] == "not_run"
    assert generated["metadata"]["provenance"]["generator_model"] == "fixture-model"
    assert generated["metadata"]["provenance"]["generator_version"] == "2026-08-07"


def test_normal_generation_falls_back_to_pro_and_records_provenance(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    blueprint = root / "tests" / "fixtures" / "blueprints" / "valid" / "no_tool.json"
    output = tmp_path / "staging" / "fallback.jsonl"

    class FailingFlash:
        model = "deepseek-v4-flash"
        calls = 0

        def require_configured(self):
            return None

        def generate_language_plan(self, blueprint):
            self.calls += 1
            raise ProviderError("primary deterministic failure")

    class PassingPro:
        model = "deepseek-v4-pro"

        def generate_language_plan(self, blueprint):
            return ProviderResponse(
                {
                    "user_messages": ["Merhaba"],
                    "intermediate_assistant_response": None,
                    "final_response": "Merhaba!",
                },
                ModelIdentity("deepseek", self.model, "pro-snapshot", "dataset_language_generator"),
                usage={"total_tokens": 10},
            )

    flash = FailingFlash()
    pro = PassingPro()
    monkeypatch.setenv("MAGIBU_TOOLCALL_RETRY_BASE_SECONDS", "0")
    monkeypatch.setattr("tool_call_tr.cli.DeepSeekIntegration.from_settings", lambda settings: flash)
    monkeypatch.setattr("tool_call_tr.cli._deepseek_fallback_provider", lambda settings, primary: pro)
    monkeypatch.setattr("tool_call_tr.cli.dataset_record_paths", lambda project_root: [])
    assert main([
        "dataset", "generate", str(blueprint),
        "--job-id", "dataset-fallback-001",
        "--runs-dir", str(tmp_path / "runs"),
        "--output", str(output),
        "--timestamp", "2026-08-07T00:00:00+00:00",
        "--execute-live",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider_fallbacks_used"] == 1
    assert flash.calls == 3
    generated = json.loads(output.read_text(encoding="utf-8"))
    provenance = generated["metadata"]["provenance"]
    assert provenance["generator_model"] == "deepseek-v4-pro"
    fallback = [
        item for item in provenance["transformation_history"]
        if item["action"] == "generation_provider_fallback"
    ]
    assert len(fallback) == 1
    assert "from_model=deepseek-v4-flash" in fallback[0]["details"]
    assert "to_model=deepseek-v4-pro" in fallback[0]["details"]
