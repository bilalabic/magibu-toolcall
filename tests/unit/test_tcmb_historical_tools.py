"""Smoke and boundary tests for the three Paket 4 TCMB exchange-rate tools."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import shutil
import socket
from typing import Any

import pytest
from jsonschema.exceptions import ValidationError

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
    MockAdapter,
)
from tool_call_tr.execution.local import finance_tcmb_historical as tcmb
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registry" / "proposals" / "finance_tcmb_historical.jsonl"
FIXTURES_DIR = ROOT / "registry" / "proposals" / "fixtures"
BLUEPRINT_PATH = ROOT / "blueprints" / "finance_tcmb_historical.jsonl"
SNAPSHOT_ROOT = ROOT / "data" / "snapshots" / "tcmb" / "exchange_rates" / "v1"
CONVERSION_SCRIPT = ROOT / "scripts" / "snapshots" / "finance_tcmb_historical.py"

CURRENT_RATES_FIXTURES = (
    "finance.tcmb.compare_current_rates.usd_eur.forex_selling",
    "finance.tcmb.compare_current_rates.usd_eur_gbp.forex_buying",
)


def registry() -> ToolRegistry:
    return ToolRegistry.load(REGISTRY_PATH, fixtures_dir=FIXTURES_DIR)


def execute_local(function_name: str, arguments: dict[str, Any]):
    engine = ExecutionEngine(registry(), ExecutionRouter([LocalExecutableAdapter()]))
    return engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name=function_name,
            arguments=arguments,
            execution_type=ExecutionType.LOCAL_EXECUTABLE,
        )
    )


def execute_mock(arguments: dict[str, Any]):
    loaded = registry()
    adapter = MockAdapter.from_registry(loaded, list(CURRENT_RATES_FIXTURES))
    engine = ExecutionEngine(loaded, ExecutionRouter([adapter]))
    return engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name="finance_compare_current_rates",
            arguments=arguments,
            execution_type=ExecutionType.MOCK,
        )
    )


def execute(function_name: str, arguments: dict[str, Any]):
    if function_name == "finance_compare_current_rates":
        return execute_mock(arguments)
    return execute_local(function_name, arguments)


def test_registry_declares_two_local_tools_and_one_fixture_tool() -> None:
    loaded = registry()

    assert len(loaded.records) == 3
    for tool_id in ("finance.search_historical_rates.v1", "finance.compare_historical_rates.v1"):
        tool = loaded.by_tool_id(tool_id)
        assert tool["execution"]["default_type"] == "local_executable"
        assert tool["execution"]["supported_types"] == ["local_executable"]
        assert tool["execution"]["fixture_ids"] == []

    current = loaded.by_tool_id("finance.compare_current_rates.v1")
    assert current["execution"]["default_type"] == "mock"
    assert current["execution"]["supported_types"] == ["mock"]
    assert tuple(current["execution"]["fixture_ids"]) == CURRENT_RATES_FIXTURES
    assert all(record["access"]["authentication"] == "none" for record in loaded.records)
    assert all(record["risks"]["personal_data"] is False for record in loaded.records)


def test_snapshot_covers_every_published_bulletin_day_in_the_quarter() -> None:
    with (SNAPSHOT_ROOT / "exchange_rates_2026_q2.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    days = sorted({row["date"] for row in rows})
    currencies = {row["currency_code"] for row in rows}

    assert len(days) == 58
    assert days[0] == "2026-04-01" and days[-1] == "2026-06-30"
    assert len(currencies) == 21
    # XDR publishes no selling rate, so a half-filled pair never enters the snapshot.
    assert "XDR" not in currencies
    assert len(rows) == 58 * 21
    assert all(float(row["forex_buying"]) < float(row["forex_selling"]) for row in rows)
    # Non-publication days are absent rather than carried forward.
    assert {"2026-04-23", "2026-05-01", "2026-05-19", "2026-05-27"}.isdisjoint(days)


def test_provenance_declares_every_raw_bulletin() -> None:
    provenance = json.loads((SNAPSHOT_ROOT / "provenance.json").read_text(encoding="utf-8"))
    raw_files = sorted(path.name for path in (SNAPSHOT_ROOT / "raw").glob("*.xml"))

    assert provenance["snapshot_version"] == "tcmb-exchange-rates-2026-q2-v1"
    assert provenance["provider"] == "TCMB"
    assert len(provenance["sources"]) == len(raw_files) == 58
    assert sorted(entry["raw_file"].removeprefix("raw/") for entry in provenance["sources"]) == raw_files
    assert {entry["label"] for entry in provenance["sources"]} == {
        entry["release_date"] for entry in provenance["sources"]
    }
    assert all(entry["source_url"].startswith("https://www.tcmb.gov.tr/kurlar/") for entry in provenance["sources"])


def test_conversion_script_reproduces_the_committed_data_file() -> None:
    """A reviewer must be able to rebuild the CSV instead of trusting it."""

    spec = importlib.util.spec_from_file_location("finance_tcmb_conversion", CONVERSION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rebuilt = module.build_csv(SNAPSHOT_ROOT / "raw")

    assert rebuilt == (SNAPSHOT_ROOT / "exchange_rates_2026_q2.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("arguments", "expected_count", "expected_first", "expected_unit"),
    (
        (
            {"currency_code": "USD", "start_date": "2026-04-01", "end_date": "2026-04-10", "rate_type": "forex_selling"},
            8,
            44.4738,
            1,
        ),
        (
            {"currency_code": "JPY", "start_date": "2026-06-29", "end_date": "2026-06-30", "rate_type": "forex_buying"},
            2,
            28.6968,
            100,
        ),
    ),
)
def test_search_smoke_returns_published_bulletin_rates(
    arguments: dict[str, Any],
    expected_count: int,
    expected_first: float,
    expected_unit: int,
) -> None:
    result = execute("finance_search_historical_rates", arguments)

    assert result.status == ExecutionStatus.PASSED
    assert result.data["count"] == expected_count == len(result.data["rates"])
    assert result.data["rates"][0]["rate"] == expected_first
    # JPY is published per 100 units, so the multiplier travels with the answer.
    assert result.data["currency_unit"] == expected_unit
    assert result.data["unit"] == "try_per_currency_unit"
    assert result.data["source"]["release_id"] == "2026/62-2026/119"
    assert result.data["highest"]["rate"] == max(item["rate"] for item in result.data["rates"])
    assert result.data["lowest"]["rate"] == min(item["rate"] for item in result.data["rates"])


def test_search_over_a_closed_period_is_an_empty_answer_not_a_failure() -> None:
    """26-31 May 2026 is inside the window but holds no bulletin."""

    result = execute(
        "finance_search_historical_rates",
        {"currency_code": "EUR", "start_date": "2026-05-26", "end_date": "2026-05-31", "rate_type": "forex_selling"},
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["count"] == 0
    assert result.data["rates"] == []
    assert result.data["highest"] is None and result.data["lowest"] is None
    assert result.data["currency_unit"] == 1


@pytest.mark.parametrize(
    "arguments",
    (
        {"currency_code": "USD", "start_date": "2026-03-31", "end_date": "2026-04-10", "rate_type": "forex_selling"},
        {"currency_code": "USD", "start_date": "2026-06-01", "end_date": "2026-07-01", "rate_type": "forex_selling"},
        {"currency_code": "USD", "start_date": "2026-06-10", "end_date": "2026-06-01", "rate_type": "forex_selling"},
    ),
)
def test_search_refuses_dates_outside_the_pinned_window(arguments: dict[str, Any]) -> None:
    result = execute("finance_search_historical_rates", arguments)

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("coverage_error:")


def test_compare_smoke_reports_change_per_currency() -> None:
    result = execute(
        "finance_compare_historical_rates",
        {"currency_codes": ["USD", "EUR"], "dates": ["2026-04-01", "2026-06-30"], "rate_type": "forex_selling"},
    )

    assert result.status == ExecutionStatus.PASSED
    by_code = {item["currency_code"]: item for item in result.data["comparisons"]}
    assert set(by_code) == {"EUR", "USD"}
    assert by_code["USD"]["change"] == 2.1848
    assert by_code["USD"]["change_percent"] == 4.91
    assert by_code["EUR"]["change"] == 1.6109
    assert by_code["EUR"]["change_percent"] == 3.12
    assert result.data["dates"] == ["2026-04-01", "2026-06-30"]


def test_compare_leaves_change_empty_for_a_single_date() -> None:
    result = execute(
        "finance_compare_historical_rates",
        {"currency_codes": ["USD", "JPY"], "dates": ["2026-06-30"], "rate_type": "forex_buying"},
    )

    assert result.status == ExecutionStatus.PASSED
    assert all(item["change"] is None and item["change_percent"] is None for item in result.data["comparisons"])
    # Rates of different published units are listed side by side, never subtracted.
    assert {item["currency_unit"] for item in result.data["comparisons"]} == {1, 100}


def test_compare_refuses_a_day_without_a_bulletin() -> None:
    result = execute(
        "finance_compare_historical_rates",
        {"currency_codes": ["USD"], "dates": ["2026-05-18", "2026-05-19"], "rate_type": "forex_selling"},
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("lookup_error:")
    assert "2026-05-19" in result.error


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("finance_search_historical_rates", {"start_date": "2026-04-01", "end_date": "2026-04-10", "rate_type": "forex_selling"}),
        ("finance_search_historical_rates", {"currency_code": "TRY", "start_date": "2026-04-01", "end_date": "2026-04-10", "rate_type": "forex_selling"}),
        ("finance_search_historical_rates", {"currency_code": "USD", "start_date": "01.04.2026", "end_date": "2026-04-10", "rate_type": "forex_selling"}),
        ("finance_search_historical_rates", {"currency_code": "USD", "start_date": "2026-04-01", "end_date": "2026-04-10", "rate_type": "banknote_selling"}),
        ("finance_compare_historical_rates", {"currency_codes": ["USD"], "rate_type": "forex_selling"}),
        ("finance_compare_historical_rates", {"currency_codes": [], "dates": ["2026-04-01"], "rate_type": "forex_selling"}),
        ("finance_compare_historical_rates", {"currency_codes": ["USD", "USD"], "dates": ["2026-04-01"], "rate_type": "forex_selling"}),
        ("finance_compare_current_rates", {"currency_codes": ["USD"], "rate_type": "forex_selling"}),
        ("finance_compare_current_rates", {"currency_codes": ["USD", "EUR"]}),
    ),
)
def test_schema_rejects_missing_or_invalid_arguments(function_name: str, arguments: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        execute(function_name, arguments)


@pytest.mark.parametrize(
    ("arguments", "expected_fixture", "expected_count"),
    (
        (
            {"currency_codes": ["USD", "EUR"], "rate_type": "forex_selling"},
            "finance.tcmb.compare_current_rates.usd_eur.forex_selling",
            2,
        ),
        (
            {"currency_codes": ["USD", "EUR", "GBP"], "rate_type": "forex_buying"},
            "finance.tcmb.compare_current_rates.usd_eur_gbp.forex_buying",
            3,
        ),
    ),
)
def test_current_rate_comparison_serves_the_frozen_bulletin(
    arguments: dict[str, Any],
    expected_fixture: str,
    expected_count: int,
) -> None:
    result = execute_mock(arguments)

    assert result.status == ExecutionStatus.PASSED
    assert result.fixture_id == expected_fixture
    assert result.data["date"] == "2026-08-14"
    assert result.data["bulletin_no"] == "2026/151"
    assert result.data["count"] == expected_count == len(result.data["rates"])
    assert result.data["source"]["release_id"] == "2026/151"


def test_unknown_argument_combination_reports_a_missing_fixture() -> None:
    result = execute_mock({"currency_codes": ["USD", "CHF"], "rate_type": "forex_selling"})

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "mock_fixture_not_found"


def test_unavailable_snapshot_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    copied = tmp_path / "exchange_rates_v1"
    shutil.copytree(SNAPSHOT_ROOT, copied)
    monkeypatch.setattr(tcmb, "SNAPSHOT_ROOT", copied)
    (copied / "exchange_rates_2026_q2.csv").unlink()

    result = execute(
        "finance_search_historical_rates",
        {"currency_code": "USD", "start_date": "2026-04-01", "end_date": "2026-04-10", "rate_type": "forex_selling"},
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("snapshot_error:")


def test_local_executors_do_not_open_network_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("local TCMB executor attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden_connection)

    assert execute(
        "finance_search_historical_rates",
        {"currency_code": "USD", "start_date": "2026-06-01", "end_date": "2026-06-30", "rate_type": "forex_buying"},
    ).status == ExecutionStatus.PASSED
    assert execute(
        "finance_compare_historical_rates",
        {"currency_codes": ["EUR"], "dates": ["2026-04-01", "2026-06-30"], "rate_type": "forex_selling"},
    ).status == ExecutionStatus.PASSED


def test_blueprints_validate_and_match_their_declared_execution() -> None:
    loaded_registry = registry()
    validator = RuleBasedValidator(registry=loaded_registry)
    blueprints = [
        json.loads(line)
        for line in BLUEPRINT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(blueprints) == 4
    assert {blueprint["metadata"]["main_category"] for blueprint in blueprints} == {
        "single_tool",
        "missing_parameter",
    }
    for blueprint in blueprints:
        report = validator.validate_record("blueprint", blueprint)
        assert report.valid, report.human()
        if blueprint["expected_behavior"] != "tool_call":
            assert blueprint["expected_tool_calls"] == []
            assert blueprint["missing_parameters"]
            continue
        call = blueprint["expected_tool_calls"][0]["function"]
        result = execute(call["name"], call["arguments"])
        assert result.status == ExecutionStatus.PASSED
        assert result.data == blueprint["expected_tool_result"]
