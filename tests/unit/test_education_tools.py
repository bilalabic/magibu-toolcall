"""Smoke tests for Umay Şamlı's deterministic university tool proposals."""

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


# Resolve all contribution paths from the repository root so the tests work
# regardless of the directory from which pytest is started.
ROOT = Path(__file__).resolve().parents[2]
PROPOSAL_REGISTRY = ROOT / "registry" / "proposals" / "registry.jsonl"
BLUEPRINT_PATH = ROOT / "blueprints" / "education_umay.jsonl"

# Every fixture declared by the two education proposal records is exercised by
# the execution smoke test below. Keeping the IDs together also makes additions
# or removals from this contribution visible in one place.
FIXTURE_IDS = (
    "education.announcements.category.academic",
    "education.announcements.date.2026-08",
    "education.exam_schedule.course.ceng101",
    "education.exam_schedule.program.computer_engineering",
)


def proposal_registry() -> ToolRegistry:
    """Load the proposal registry that owns the education tool contracts."""

    return ToolRegistry.load(PROPOSAL_REGISTRY)


def mock_engine(registry: ToolRegistry) -> ExecutionEngine:
    """Build the same registry-backed mock execution stack used by the CLI."""

    adapter = MockAdapter.from_registry(registry, list(FIXTURE_IDS))
    return ExecutionEngine(registry, ExecutionRouter([adapter]))


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_education_fixtures_execute_successfully(fixture_id: str) -> None:
    """Every declared fixture should produce its exact schema-valid result."""

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

    # These checks cover routing, execution mode, fixture selection, input
    # validation, and output validation through the real ExecutionEngine.
    assert result.status == ExecutionStatus.PASSED
    assert result.execution_type == ExecutionType.MOCK
    assert result.fixture_id == fixture_id
    assert result.data == fixture["result"]


@pytest.mark.parametrize(
    "fixture_id",
    (
        "education.announcements.category.academic",
        "education.exam_schedule.course.ceng101",
    ),
)
def test_education_fixture_cli_smoke(fixture_id: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Representative announcement and exam fixtures should work through the CLI."""

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

    # The CLI must report both process success and normalized execution success.
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["execution_type"] == "mock"
    assert payload["fixture_id"] == fixture_id


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("education_list_announcements", {"category": "unknown"}),
        ("education_get_exam_schedule", {"filter_type": "course"}),
    ),
)
def test_education_tools_reject_invalid_or_missing_arguments(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    """Input schemas should reject unknown enums and missing required fields."""

    registry = proposal_registry()

    # Argument validation happens before a request reaches the mock adapter.
    with pytest.raises(JsonSchemaValidationError):
        mock_engine(registry).execute(
            ExecutionRequest("call_001", function_name, arguments, ExecutionType.MOCK)
        )


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("education_list_announcements", {"category": "event", "limit": 5}),
        (
            "education_get_exam_schedule",
            {"filter_type": "course", "filter_value": "CENG999"},
        ),
    ),
)
def test_education_tools_fail_when_no_exact_fixture_matches(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    """A valid request must not silently reuse a fixture for different arguments."""

    registry = proposal_registry()

    # Mock execution is intentionally keyed by the complete argument object.
    result = mock_engine(registry).execute(
        ExecutionRequest("call_001", function_name, arguments, ExecutionType.MOCK)
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "mock_fixture_not_found"
    assert result.data is None


def test_education_blueprints_validate_and_match_their_fixtures() -> None:
    """Blueprint calls and expected results should stay synchronized with fixtures."""

    registry = proposal_registry()
    validator = RuleBasedValidator(registry=registry)
    blueprints = [
        json.loads(line)
        for line in BLUEPRINT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Paket 12 requires at least one blueprint for each of its two tools.
    assert len(blueprints) == 2
    for blueprint in blueprints:
        # RuleBasedValidator covers the shared schema plus registry-aware rules.
        report = validator.validate_record("blueprint", blueprint)
        assert report.valid, report.human()

        # The provenance source_example_id deliberately points at the fixture
        # that supplies this blueprint's deterministic arguments and result.
        fixture_id = blueprint["metadata"]["provenance"]["source_example_id"]
        fixture = registry.load_fixture(fixture_id)
        expected_call = blueprint["expected_tool_calls"][0]["function"]
        assert fixture["function_name"] == expected_call["name"]
        assert fixture["arguments"] == expected_call["arguments"]
        assert fixture["result"] == blueprint["expected_tool_result"]
