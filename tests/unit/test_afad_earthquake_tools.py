from __future__ import annotations

import json
from pathlib import Path

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
PROPOSAL_REGISTRY = ROOT / "registry" / "proposals" / "registry.jsonl"

FIXTURE_IDS = (
    "earthquake.afad.list_recent.v1",
    "earthquake.afad.event_details.v1",
)

BLUEPRINT_CASES = (
    ("earthquake_list_recent.json", "tool_call", ()),
    ("earthquake_get_event_details.json", "tool_call", ()),
    ("earthquake_list_recent_missing_limit.json", "request_information", ("limit",)),
    (
        "earthquake_get_event_details_missing_event_id.json",
        "request_information",
        ("event_id",),
    ),
)


def load_registry() -> ToolRegistry:
    return ToolRegistry.load(PROPOSAL_REGISTRY)


def build_engine(registry: ToolRegistry) -> ExecutionEngine:
    adapter = MockAdapter.from_registry(registry, list(FIXTURE_IDS))
    return ExecutionEngine(registry, ExecutionRouter([adapter]))


@pytest.mark.parametrize(
    ("filename", "expected_behavior", "missing_parameters"),
    BLUEPRINT_CASES,
)
def test_afad_blueprints_are_valid_and_follow_expected_behavior(
    filename: str,
    expected_behavior: str,
    missing_parameters: tuple[str, ...],
) -> None:
    registry = load_registry()
    blueprint = json.loads(
        (ROOT / "blueprints" / filename).read_text(encoding="utf-8")
    )

    report = RuleBasedValidator(registry=registry).validate_record(
        "blueprint",
        blueprint,
    )

    assert report.valid, report.human()
    assert blueprint["expected_behavior"] == expected_behavior
    assert blueprint["missing_parameters"] == list(missing_parameters)

    if expected_behavior == "request_information":
        assert blueprint["expected_tool_calls"] == []
        assert blueprint["expected_tool_result"] is None
        assert blueprint["metadata"]["main_category"] == "missing_parameter"
        assert blueprint["metadata"]["secondary_tags"] == ["clarification"]
        assert blueprint["metadata"]["intended_execution_type"] == "not_applicable"


def test_afad_registry_contains_two_mock_only_candidate_tools() -> None:
    registry = load_registry()

    assert len(registry.records) == 2

    for function_name in (
        "earthquake_list_recent",
        "earthquake_get_event_details",
    ):
        tool = registry.by_function_name(function_name)

        assert tool["lifecycle"] == "candidate"
        assert tool["execution"]["default_type"] == "mock"
        assert tool["execution"]["supported_types"] == ["mock"]
        assert tool["access"]["authentication"] == "not_applicable"
        assert "http" not in tool["execution"]


def test_afad_event_id_schemas_use_the_same_constraints() -> None:
    registry = load_registry()

    list_tool = registry.by_function_name("earthquake_list_recent")
    detail_tool = registry.by_function_name("earthquake_get_event_details")

    list_event_id = list_tool["output_schema"]["properties"]["events"]["items"][
        "properties"
    ]["event_id"]
    detail_input_id = detail_tool["function"]["parameters"]["properties"][
        "event_id"
    ]
    detail_output_id = detail_tool["output_schema"]["properties"]["event"][
        "properties"
    ]["event_id"]

    for field in ("type", "minLength", "maxLength", "pattern"):
        assert list_event_id[field] == detail_input_id[field]
        assert detail_output_id[field] == detail_input_id[field]


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_afad_fixtures_are_declared_and_schema_valid(fixture_id: str) -> None:
    registry = load_registry()
    fixture = registry.load_fixture(fixture_id)

    assert fixture["fixture_id"] == fixture_id

    provenance = fixture["provenance"].lower()
    assert "fixture_version=v1" in provenance
    assert "data_kind=synthetic" in provenance
    assert "live_api_status=hold" in provenance


def test_afad_list_and_detail_fixtures_reference_same_event() -> None:
    registry = load_registry()

    list_fixture = registry.load_fixture("earthquake.afad.list_recent.v1")
    detail_fixture = registry.load_fixture("earthquake.afad.event_details.v1")

    listed_events = list_fixture["result"]["events"]

    assert list_fixture["result"]["count"] == len(listed_events)
    assert listed_events[0] == detail_fixture["result"]["event"]
    assert "fixture" not in listed_events[0]["event_id"].lower()
    assert "örnek" not in listed_events[0]["location"].lower()
    assert (
        detail_fixture["arguments"]["event_id"]
        == detail_fixture["result"]["event"]["event_id"]
    )


@pytest.mark.parametrize(
    ("fixture_id", "function_name"),
    [
        ("earthquake.afad.list_recent.v1", "earthquake_list_recent"),
        (
            "earthquake.afad.event_details.v1",
            "earthquake_get_event_details",
        ),
    ],
)
def test_afad_mock_happy_paths_pass(
    fixture_id: str,
    function_name: str,
) -> None:
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


def test_unknown_event_id_fails_closed_without_fallback() -> None:
    registry = load_registry()
    engine = build_engine(registry)

    result = engine.execute(
        ExecutionRequest(
            call_id="call_001",
            function_name="earthquake_get_event_details",
            arguments={"event_id": "unknown-event"},
            execution_type=ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.execution_type == ExecutionType.MOCK
    assert result.error == "mock_fixture_not_found"
    assert result.fixture_id is None


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    [
        (
            "earthquake_list_recent",
            {"hours": 24, "min_magnitude": 3},
        ),
        (
            "earthquake_list_recent",
            {"hours": 24, "min_magnitude": 3, "limit": 0},
        ),
        (
            "earthquake_get_event_details",
            {"event_id": ""},
        ),
    ],
)
def test_invalid_afad_arguments_are_rejected_before_execution(
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
