"""Smoke tests for the university study-room reservation simulator."""

from __future__ import annotations

from pathlib import Path

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    StatefulSimulationAdapter,
)
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]

PROPOSAL_REGISTRY = (
    ROOT
    / "registry"
    / "proposals"
    / "education_study_room.jsonl"
)

FUNCTION_NAME = "education_book_study_room"


def build_engine() -> ExecutionEngine:
    """Create an execution engine backed by the stateful simulator."""

    registry = ToolRegistry.load(PROPOSAL_REGISTRY)

    adapter = StatefulSimulationAdapter()

    router = ExecutionRouter([adapter])

    return ExecutionEngine(registry, router)


def execute(
    engine: ExecutionEngine,
    *,
    room_id: str = "study_b201",
    date: str = "2026-09-17",
    start_time: str = "10:00",
    end_time: str = "11:00",
    attendee_count: int = 3,
    confirmed: bool,
    call_id: str = "call_001",
):
    """Execute one study-room reservation request."""

    return engine.execute(
        ExecutionRequest(
            call_id=call_id,
            function_name=FUNCTION_NAME,
            arguments={
                "room_id": room_id,
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "attendee_count": attendee_count,
                "confirmed": confirmed,
            },
            execution_type=ExecutionType.FULLY_SIMULATED,
        )
    )


def test_confirmation_required_does_not_change_state() -> None:
    """No reservation should be created before explicit confirmation."""

    engine = build_engine()

    first_result = execute(
        engine,
        confirmed=False,
    )

    assert first_result.status == ExecutionStatus.PASSED
    assert first_result.data["status"] == "confirmation_required"
    assert first_result.data["available"] is True
    assert first_result.data["confirmation_required"] is True
    assert first_result.data["reservation_id"] is None

    confirmed_result = execute(
        engine,
        confirmed=True,
        call_id="call_002",
    )

    assert confirmed_result.status == ExecutionStatus.PASSED
    assert confirmed_result.data["status"] == "confirmed"
    assert confirmed_result.data["reservation_id"] == "reservation_002"


def test_confirmed_reservation_changes_state_and_causes_conflict() -> None:
    """A confirmed reservation should make the same slot unavailable."""

    engine = build_engine()

    first_result = execute(
        engine,
        confirmed=True,
    )

    assert first_result.status == ExecutionStatus.PASSED
    assert first_result.data["status"] == "confirmed"
    assert first_result.data["reservation_id"] == "reservation_002"

    second_result = execute(
        engine,
        confirmed=True,
        call_id="call_002",
    )

    assert second_result.status == ExecutionStatus.PASSED
    assert second_result.data["status"] == "conflict"
    assert second_result.data["available"] is False
    assert second_result.data["conflict_with"] == "reservation_002"


def test_existing_reservation_causes_conflict() -> None:
    """The seeded A101 reservation should block overlapping requests."""

    engine = build_engine()

    result = execute(
        engine,
        room_id="study_a101",
        date="2026-09-17",
        start_time="14:30",
        end_time="14:45",
        attendee_count=2,
        confirmed=True,
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["status"] == "conflict"
    assert result.data["available"] is False
    assert result.data["conflict_with"] == "reservation_001"


def test_reset_restores_initial_state() -> None:
    """Reset should remove reservations created during the simulation."""

    engine = build_engine()

    first_result = execute(
        engine,
        confirmed=True,
    )

    assert first_result.data["status"] == "confirmed"
    assert first_result.data["reservation_id"] == "reservation_002"

    engine.router.reset(ExecutionType.FULLY_SIMULATED)

    after_reset = execute(
        engine,
        confirmed=True,
        call_id="call_002",
    )

    assert after_reset.status == ExecutionStatus.PASSED
    assert after_reset.data["status"] == "confirmed"
    assert after_reset.data["reservation_id"] == "reservation_002"


def test_room_capacity_is_enforced() -> None:
    """Reservations above the room capacity should be rejected."""

    engine = build_engine()

    result = execute(
        engine,
        room_id="study_a101",
        date="2026-09-18",
        start_time="10:00",
        end_time="11:00",
        attendee_count=5,
        confirmed=True,
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["status"] == "capacity_exceeded"
    assert result.data["available"] is False
    assert result.data["reservation_id"] is None