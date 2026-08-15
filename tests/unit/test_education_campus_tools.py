"""Smoke tests for Seda Nur Yazıcı's deterministic university campus tool proposals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from tool_call_tr.cli import main
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
PROPOSAL_REGISTRY = ROOT / "registry" / "proposals" / "education_university_campus.jsonl"
BLUEPRINT_PATH = ROOT / "blueprints" / "education_university_campus.jsonl"

FIXTURE_IDS = (
    "education.meal_menu.main.2026-08-18",
    "education.academic_calendar.registration.2026-09",
)


def proposal_registry() -> ToolRegistry:
    return ToolRegistry.load(PROPOSAL_REGISTRY)


def mock_engine(registry: ToolRegistry) -> ExecutionEngine:
    adapter = MockAdapter.from_registry(registry, list(FIXTURE_IDS))
    return ExecutionEngine(registry, ExecutionRouter([adapter]))


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_education_campus_fixtures_execute_successfully(fixture_id: str) -> None:
    registry = proposal_registry()
    fixture = registry.load_fixture(fixture_id)
    result = mock_engine(registry).execute(
        ExecutionRequest(
            "call_001",
            fixture["function_name"],
            fixture["arguments"],
            ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.execution_type == ExecutionType.MOCK
    assert result.fixture_id == fixture_id
    assert result.data == fixture["result"]


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_education_campus_fixture_cli_smoke(
    fixture_id: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([
        "tool",
        "run-fixture",
        fixture_id,
        "--registry",
        str(PROPOSAL_REGISTRY),
        "--mode",
        "mock",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["execution_type"] == "mock"
    assert payload["fixture_id"] == fixture_id


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("education_get_meal_menu", {"campus": "main"}),
        ("education_get_meal_menu", {"campus": "unknown", "date": "2026-08-18"}),
        ("education_get_academic_calendar", {"start_date": "2026-09-01"}),
    ),
)
def test_education_campus_tools_reject_invalid_or_missing_arguments(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    registry = proposal_registry()

    with pytest.raises(JsonSchemaValidationError):
        mock_engine(registry).execute(
            ExecutionRequest("call_001", function_name, arguments, ExecutionType.MOCK)
        )


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        (
            "education_get_meal_menu",
            {"campus": "north", "date": "2026-08-18"},
        ),
        (
            "education_get_academic_calendar",
            {
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
                "event_type": "registration",
            },
        ),
    ),
)
def test_education_campus_tools_fail_when_no_exact_fixture_matches(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    registry = proposal_registry()
    result = mock_engine(registry).execute(
        ExecutionRequest("call_001", function_name, arguments, ExecutionType.MOCK)
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "mock_fixture_not_found"
    assert result.data is None


def test_education_campus_blueprints_validate_and_match_their_fixtures() -> None:
    registry = proposal_registry()
    validator = RuleBasedValidator(registry=registry)
    blueprints = [
        json.loads(line)
        for line in BLUEPRINT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(blueprints) == 2
    for blueprint in blueprints:
        report = validator.validate_record("blueprint", blueprint)
        assert report.valid, report.human()

        fixture_id = blueprint["metadata"]["provenance"]["source_example_id"]
        fixture = registry.load_fixture(fixture_id)
        expected_call = blueprint["expected_tool_calls"][0]["function"]

        assert fixture["function_name"] == expected_call["name"]
        assert fixture["arguments"] == expected_call["arguments"]
        assert fixture["result"] == blueprint["expected_tool_result"]
