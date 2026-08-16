from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest
from jsonschema.exceptions import ValidationError

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    MockAdapter,
)
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.validation import RuleBasedValidator


ROOT = Path(__file__).resolve().parents[2]
PROPOSAL_REGISTRY = ROOT / "registry" / "proposals" / "finance_tcmb.jsonl"
BLUEPRINT_FILE = ROOT / "blueprints" / "finance_tcmb.jsonl"
FIXTURE_DIR = ROOT / "registry" / "proposals" / "fixtures"
NORMALIZER_SCRIPT = ROOT / "scripts" / "fixtures" / "finance_tcmb.py"

USD_FIXTURE = "finance.tcmb.exchange_rate.usd_forex_selling.v1"
RON_FIXTURE = "finance.tcmb.exchange_rate.ron_banknote_selling.v1"
LIST_FIXTURE = "finance.tcmb.exchange_rates.forex_selling_top5.v1"
FIXTURE_IDS = (USD_FIXTURE, RON_FIXTURE, LIST_FIXTURE)

BLUEPRINT_CASES = (
    ("bp_finance_get_exchange_rate_001", "tool_call", ()),
    ("bp_finance_list_exchange_rates_001", "tool_call", ()),
    (
        "bp_finance_get_exchange_rate_missing_rate_type_001",
        "request_information",
        ("rate_type",),
    ),
    (
        "bp_finance_get_exchange_rate_unavailable_banknote_001",
        "tool_call",
        (),
    ),
    ("bp_finance_unsupported_currency_001", "cannot_answer", ()),
)


def load_registry() -> ToolRegistry:
    return ToolRegistry.load(PROPOSAL_REGISTRY, fixtures_dir=FIXTURE_DIR)


def load_blueprints() -> dict[str, dict]:
    records = [
        json.loads(line)
        for line in BLUEPRINT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {record["id"]: record for record in records}


def load_normalizer() -> ModuleType:
    """Import the fixture converter, which lives outside the installed package."""

    specification = importlib.util.spec_from_file_location(
        "finance_tcmb_normalizer",
        NORMALIZER_SCRIPT,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    # `dataclasses` resolves annotations through `sys.modules`, so a converter
    # loaded by path must be registered before it is executed.
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def load_bulletin():
    normalizer = load_normalizer()
    return normalizer, normalizer.parse_bulletin(
        normalizer.BULLETIN_FILE.read_text(encoding="utf-8")
    )


def build_engine(registry: ToolRegistry) -> ExecutionEngine:
    adapter = MockAdapter.from_registry(registry, list(FIXTURE_IDS))
    return ExecutionEngine(registry, ExecutionRouter([adapter]))


@pytest.mark.parametrize(
    ("blueprint_id", "expected_behavior", "missing_parameters"),
    BLUEPRINT_CASES,
)
def test_tcmb_blueprints_are_valid_and_follow_expected_behavior(
    blueprint_id: str,
    expected_behavior: str,
    missing_parameters: tuple[str, ...],
) -> None:
    registry = load_registry()
    blueprint = load_blueprints()[blueprint_id]

    report = RuleBasedValidator(registry=registry).validate_record(
        "blueprint",
        blueprint,
    )

    assert report.valid, report.human()
    assert blueprint["expected_behavior"] == expected_behavior
    assert blueprint["missing_parameters"] == list(missing_parameters)

    if expected_behavior != "tool_call":
        assert blueprint["expected_tool_calls"] == []
        assert blueprint["expected_tool_result"] is None
        assert blueprint["metadata"]["intended_execution_type"] == "not_applicable"


def test_tcmb_registry_contains_two_mock_only_candidate_tools() -> None:
    registry = load_registry()

    assert len(registry.records) == 2

    for function_name in (
        "finance_get_exchange_rate",
        "finance_list_exchange_rates",
    ):
        tool = registry.by_function_name(function_name)

        assert tool["lifecycle"] == "candidate"
        assert tool["execution"]["default_type"] == "mock"
        assert tool["execution"]["supported_types"] == ["mock"]
        assert tool["access"]["credential_env_vars"] == []
        assert "http" not in tool["execution"]


def test_tcmb_tools_share_one_rate_type_vocabulary() -> None:
    """Both tools read the same bulletin, so the kinds of rate cannot drift."""

    registry = load_registry()
    get_tool = registry.by_function_name("finance_get_exchange_rate")
    list_tool = registry.by_function_name("finance_list_exchange_rates")

    expected = ["forex_buying", "forex_selling", "banknote_buying", "banknote_selling"]
    get_input = get_tool["function"]["parameters"]["properties"]["rate_type"]["enum"]
    list_input = list_tool["function"]["parameters"]["properties"]["rate_type"]["enum"]

    assert get_input == list_input == expected
    assert get_tool["output_schema"]["properties"]["rate_type"]["enum"] == expected
    assert list_tool["output_schema"]["properties"]["rate_type"]["enum"] == expected


def test_currency_enum_matches_the_pinned_bulletin() -> None:
    """An input the bulletin cannot answer must not be accepted in the first place."""

    registry = load_registry()
    _, bulletin = load_bulletin()

    declared = registry.by_function_name("finance_get_exchange_rate")["function"][
        "parameters"
    ]["properties"]["currency_code"]["enum"]

    assert declared == [entry.currency_code for entry in bulletin.entries]


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_tcmb_fixtures_are_declared_and_schema_valid(fixture_id: str) -> None:
    registry = load_registry()
    fixture = registry.load_fixture(fixture_id)

    assert fixture["fixture_id"] == fixture_id

    provenance = fixture["provenance"].lower()
    assert "fixture_version=v1" in provenance
    assert "data_kind=synthetic" in provenance
    assert "license_review_status=pending" in provenance


def test_fixtures_are_reproducible_from_the_pinned_bulletin() -> None:
    """A reviewer can rebuild every fixture instead of trusting the committed bytes."""

    normalizer, bulletin = load_bulletin()

    rebuilt = normalizer.build_fixtures(bulletin)

    assert set(rebuilt) == set(FIXTURE_IDS)
    for fixture_id, fixture in rebuilt.items():
        committed = (FIXTURE_DIR / f"{fixture_id}.json").read_text(encoding="utf-8")
        assert normalizer.render(fixture) == committed


@pytest.mark.parametrize(
    ("fixture_id", "function_name"),
    [
        (USD_FIXTURE, "finance_get_exchange_rate"),
        (RON_FIXTURE, "finance_get_exchange_rate"),
        (LIST_FIXTURE, "finance_list_exchange_rates"),
    ],
)
def test_tcmb_mock_happy_paths_pass(fixture_id: str, function_name: str) -> None:
    registry = load_registry()
    fixture = registry.load_fixture(fixture_id)
    engine = build_engine(registry)

    result = engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name=function_name,
            arguments=fixture["arguments"],
            execution_type=ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.execution_type == ExecutionType.MOCK
    assert result.fixture_id == fixture_id
    assert result.data == fixture["result"]


def test_unpublished_rate_is_an_answer_not_a_failure() -> None:
    """TCMB publishes no banknote quote for some currencies; that is still a result."""

    registry = load_registry()
    engine = build_engine(registry)

    result = engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name="finance_get_exchange_rate",
            arguments={"currency_code": "RON", "rate_type": "banknote_selling"},
            execution_type=ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["rate_available"] is False
    assert result.data["rate"] is None
    assert result.data["bulletin_date"] == "2026-08-14"


def test_undeclared_argument_combination_fails_closed() -> None:
    registry = load_registry()
    engine = build_engine(registry)

    result = engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name="finance_get_exchange_rate",
            arguments={"currency_code": "JPY", "rate_type": "forex_buying"},
            execution_type=ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "mock_fixture_not_found"
    assert result.fixture_id is None


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    [
        ("finance_get_exchange_rate", {"currency_code": "USD"}),
        ("finance_get_exchange_rate", {"currency_code": "GEL", "rate_type": "forex_selling"}),
        ("finance_get_exchange_rate", {"currency_code": "usd", "rate_type": "forex_selling"}),
        ("finance_get_exchange_rate", {"currency_code": "USD", "rate_type": "middle"}),
        ("finance_list_exchange_rates", {"rate_type": "forex_selling", "limit": 0}),
        ("finance_list_exchange_rates", {"rate_type": "forex_selling", "limit": 51}),
        (
            "finance_list_exchange_rates",
            {"rate_type": "forex_selling", "limit": 5, "date": "2026-08-14"},
        ),
    ],
)
def test_invalid_tcmb_arguments_are_rejected_before_execution(
    function_name: str,
    arguments: dict,
) -> None:
    registry = load_registry()
    engine = build_engine(registry)

    with pytest.raises(ValidationError):
        engine.execute(
            ExecutionRequest(
                call_id="call_001",
                function_name=function_name,
                arguments=arguments,
                execution_type=ExecutionType.MOCK,
            )
        )


def test_normalizer_keeps_the_quotation_unit_of_the_source() -> None:
    """JPY is published per 100 units; dropping that silently changes the price."""

    normalizer, bulletin = load_bulletin()

    payload = normalizer.build_rate_payload(bulletin, "JPY", "forex_selling")

    assert payload["rate"]["quotation_unit"] == 100
    assert payload["rate"]["unit"] == "TRY"


def test_normalizer_skips_currencies_without_the_requested_rate() -> None:
    normalizer, bulletin = load_bulletin()

    published = normalizer.build_list_payload(bulletin, "banknote_selling", 50)
    listed = {rate["currency_code"] for rate in published["rates"]}

    assert published["count"] == len(published["rates"])
    assert "RON" not in listed
    assert "USD" in listed


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda module, bulletin: module.build_rate_payload(bulletin, "GEL", "forex_selling"), "GEL"),
        (lambda module, bulletin: module.build_rate_payload(bulletin, "USD", "middle"), "middle"),
        (lambda module, bulletin: module.build_list_payload(bulletin, "forex_selling", 0), "limit"),
    ],
)
def test_normalizer_refuses_requests_outside_the_bulletin(call, message: str) -> None:
    normalizer, bulletin = load_bulletin()

    with pytest.raises(normalizer.BulletinError, match=message):
        call(normalizer, bulletin)


@pytest.mark.parametrize(
    "document",
    [
        "<Tarih_Date Tarih='14.08.2026'>",
        "<Tarih_Date Tarih='14.08.2026'></Tarih_Date>",
        (
            "<Tarih_Date Tarih='14.08.2026'><Currency CurrencyCode='USD'>"
            "<Unit>1</Unit><Isim>ABD DOLARI</Isim>"
            "<ForexSelling>abc</ForexSelling></Currency></Tarih_Date>"
        ),
    ],
)
def test_normalizer_rejects_a_malformed_bulletin(document: str) -> None:
    normalizer = load_normalizer()

    with pytest.raises(normalizer.BulletinError):
        normalizer.parse_bulletin(document)
