"""Smoke tests for Nur Sima Akgül's İZSU dam-levels mock tool proposal."""

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

# Resolve contribution paths from the repository root so the tests work
# regardless of the directory pytest is started from.
ROOT = Path(__file__).resolve().parents[2]
PROPOSAL_REGISTRY = ROOT / "registry" / "proposals" / "water_izsu.jsonl"

# Every fixture declared by the dam-levels proposal record is exercised below.
FIXTURE_IDS = (
    "water.dam_levels.izmir.all.2026-08-15",
    "water.dam_levels.izmir.tahtali.2026-08-15",
)


def proposal_registry() -> ToolRegistry:
    """Load the proposal registry that owns the dam-levels tool contract."""

    return ToolRegistry.load(PROPOSAL_REGISTRY)


def mock_engine(registry: ToolRegistry) -> ExecutionEngine:
    """Build the same registry-backed mock execution stack used by the CLI."""

    adapter = MockAdapter.from_registry(registry, list(FIXTURE_IDS))
    return ExecutionEngine(registry, ExecutionRouter([adapter]))


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_dam_fixtures_execute_successfully(fixture_id: str) -> None:
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

    # Covers routing, execution mode, fixture selection, input validation, and
    # output validation through the real ExecutionEngine.
    assert result.status == ExecutionStatus.PASSED
    assert result.execution_type == ExecutionType.MOCK
    assert result.fixture_id == fixture_id
    assert result.data == fixture["result"]


def test_dam_freshness_is_modelled() -> None:
    """The all-dams fixture must expose both fresh and stale measurements so the
    freshness/güncellik contract stays meaningful rather than always-fresh."""

    registry = proposal_registry()
    result = registry.load_fixture("water.dam_levels.izmir.all.2026-08-15")["result"]
    freshness_values = {dam["freshness"] for dam in result["dams"]}

    assert result["count"] == len(result["dams"])
    assert "fresh" in freshness_values
    assert "stale" in freshness_values


def test_dam_fixture_cli_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    """The representative all-dams fixture should work through the CLI."""

    exit_code = main([
        "tool",
        "run-fixture",
        "water.dam_levels.izmir.all.2026-08-15",
        "--registry",
        str(PROPOSAL_REGISTRY),
        "--mode",
        "mock",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["execution_type"] == "mock"
    assert payload["fixture_id"] == "water.dam_levels.izmir.all.2026-08-15"


def test_dam_tool_rejects_unknown_dam_enum() -> None:
    """An unsupported dam name must fail input-schema validation before the
    request ever reaches the mock adapter."""

    registry = proposal_registry()
    with pytest.raises(JsonSchemaValidationError):
        mock_engine(registry).execute(
            ExecutionRequest(
                "call_001",
                "water_get_dam_levels",
                {"dam": "Olmayan Baraj"},
                ExecutionType.MOCK,
            )
        )


def test_dam_tool_fails_when_no_exact_fixture_matches() -> None:
    """A schema-valid dam with no matching fixture yields mock_fixture_not_found
    rather than a fabricated answer."""

    registry = proposal_registry()
    result = mock_engine(registry).execute(
        ExecutionRequest(
            "call_001",
            "water_get_dam_levels",
            {"dam": "Balçova Barajı"},
            ExecutionType.MOCK,
        )
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "mock_fixture_not_found"
