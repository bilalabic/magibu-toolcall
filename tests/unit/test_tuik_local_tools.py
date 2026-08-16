"""Smoke and boundary tests for the two Paket 10 local TÜİK tools."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import socket

import pytest
from jsonschema.exceptions import ValidationError

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
)
from tool_call_tr.execution.local import demography_labor_tuik as tuik
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registry" / "proposals" / "demography_labor_tuik.jsonl"
BLUEPRINT_PATH = ROOT / "blueprints" / "demography_labor_tuik.jsonl"
SNAPSHOT_ROOT = ROOT / "data" / "snapshots" / "tuik"


def registry() -> ToolRegistry:
    return ToolRegistry.load(REGISTRY_PATH)


def execute(function_name: str, arguments: dict[str, object]):
    engine = ExecutionEngine(registry(), ExecutionRouter([LocalExecutableAdapter()]))
    return engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name=function_name,
            arguments=arguments,
            execution_type=ExecutionType.LOCAL_EXECUTABLE,
        )
    )


def test_registry_has_exactly_two_local_tools() -> None:
    loaded = registry()

    assert len(loaded.records) == 2
    for tool_id in (
        "demography.get_migration_statistics.v1",
        "labor.get_unemployment_rate.v1",
    ):
        tool = loaded.by_tool_id(tool_id)
        assert tool["execution"]["default_type"] == "local_executable"
        assert tool["execution"]["supported_types"] == ["local_executable"]
        assert tool["access"]["authentication"] == "none"


def test_downloaded_snapshots_cover_2021_through_2025() -> None:
    migration_dir = SNAPSHOT_ROOT / "migration" / "v1"
    unemployment_dir = SNAPSHOT_ROOT / "unemployment" / "v1"
    with (migration_dir / "migration_2021_2025.csv").open(encoding="utf-8", newline="") as handle:
        migration_rows = list(csv.DictReader(handle))
    with (unemployment_dir / "unemployment_2021_2025.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        unemployment_rows = list(csv.DictReader(handle))

    assert len(migration_rows) == 5 * 81
    assert {int(row["year"]) for row in migration_rows} == set(range(2021, 2026))
    assert len({(row["province"], row["year"]) for row in migration_rows}) == 5 * 81
    assert all(
        int(row["in_migration"]) - int(row["out_migration"])
        == int(row["net_migration"])
        for row in migration_rows
    )

    assert len(unemployment_rows) == 5
    assert {int(row["year"]) for row in unemployment_rows} == set(range(2021, 2026))
    assert all(0 <= float(row["unemployment_rate"]) <= 100 for row in unemployment_rows)


def test_migration_and_labor_provenance_are_separate() -> None:
    migration = json.loads(
        (SNAPSHOT_ROOT / "migration" / "v1" / "provenance.json").read_text(encoding="utf-8")
    )
    unemployment = json.loads(
        (SNAPSHOT_ROOT / "unemployment" / "v1" / "provenance.json").read_text(
            encoding="utf-8"
        )
    )

    assert migration["snapshot_version"] == "tuik-internal-migration-2021-2025-v1"
    assert unemployment["snapshot_version"] == "tuik-labor-force-annual-2021-2025-v1"
    assert {source["label"] for source in migration["sources"]} == {
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    }
    assert migration["data_file"] != unemployment["data_file"]
    assert migration["license_url"] == unemployment["license_url"]


@pytest.mark.parametrize(
    ("year", "metric", "expected_value", "expected_release"),
    (
        (2021, "net_migration", 32_098, "45869"),
        (2023, "in_migration", 232_700, "53676"),
        (2025, "net_migration_rate", 5.3, "58139"),
    ),
)
def test_migration_smoke_across_snapshot_years(
    year: int,
    metric: str,
    expected_value: int | float,
    expected_release: str,
) -> None:
    result = execute(
        "demography_get_migration_statistics",
        {"province": "ankara", "year": year, "metric": metric},
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["province"] == "Ankara"
    assert result.data["value"] == expected_value
    assert result.data["source"]["release_id"] == expected_release


@pytest.mark.parametrize(
    ("year", "expected_rate"),
    ((2021, 12.0), (2022, 10.4), (2023, 9.4), (2024, 8.7), (2025, 8.3)),
)
def test_unemployment_smoke_across_snapshot_years(year: int, expected_rate: float) -> None:
    result = execute("labor_get_unemployment_rate", {"year": year})

    assert result.status == ExecutionStatus.PASSED
    assert result.data["unemployment_rate"] == expected_rate
    assert result.data["period"] == "annual"
    assert result.data["age_group"] == "15_plus"


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("demography_get_migration_statistics", {"year": 2023, "metric": "net_migration"}),
        (
            "demography_get_migration_statistics",
            {"province": "Ankara", "year": 2020, "metric": "net_migration"},
        ),
        (
            "demography_get_migration_statistics",
            {"province": "Ankara", "year": 2023, "metric": "unknown"},
        ),
        ("labor_get_unemployment_rate", {}),
        ("labor_get_unemployment_rate", {"year": 2026}),
    ),
)
def test_schema_rejects_missing_or_invalid_arguments(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        execute(function_name, arguments)


def test_empty_migration_result_fails_cleanly() -> None:
    result = execute(
        "demography_get_migration_statistics",
        {"province": "Geçersiz İl", "year": 2023, "metric": "net_migration"},
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("lookup_error:")


def test_unavailable_snapshot_fails_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied = tmp_path / "tuik"
    shutil.copytree(SNAPSHOT_ROOT, copied)
    monkeypatch.setattr(tuik, "SNAPSHOT_ROOT", copied)
    (copied / "unemployment" / "v1" / "unemployment_2021_2025.csv").unlink()

    result = execute("labor_get_unemployment_rate", {"year": 2024})

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("snapshot_error:")


def test_local_executors_do_not_open_network_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("local TÜİK executor attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden_connection)

    assert execute(
        "demography_get_migration_statistics",
        {"province": "Ankara", "year": 2025, "metric": "net_migration"},
    ).status == ExecutionStatus.PASSED
    assert execute("labor_get_unemployment_rate", {"year": 2025}).status == ExecutionStatus.PASSED


def test_exactly_two_blueprints_validate_and_match_local_execution() -> None:
    loaded_registry = registry()
    validator = RuleBasedValidator(registry=loaded_registry)
    blueprints = [
        json.loads(line)
        for line in BLUEPRINT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(blueprints) == 2
    for blueprint in blueprints:
        report = validator.validate_record("blueprint", blueprint)
        assert report.valid, report.human()
        call = blueprint["expected_tool_calls"][0]["function"]
        result = execute(call["name"], call["arguments"])
        assert result.status == ExecutionStatus.PASSED
        assert result.data == blueprint["expected_tool_result"]
