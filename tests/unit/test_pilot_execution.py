from pathlib import Path

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    LocalExecutableAdapter,
    MockAdapter,
    StatefulSimulationAdapter,
)
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def proposal_registry() -> ToolRegistry:
    return ToolRegistry.load(ROOT / "registry" / "proposals" / "pilot_candidates.jsonl")


def test_local_pilot_fixtures_execute_exactly() -> None:
    tools = proposal_registry()
    engine = ExecutionEngine(tools, ExecutionRouter([LocalExecutableAdapter()]))
    for fixture_id in (
        "calculator.evaluate.basic",
        "calculator.convert_units.speed",
        "time.convert_timezone.istanbul_london",
        "holiday.business_day.republic_day",
    ):
        fixture = tools.load_fixture(fixture_id)
        result = engine.execute(ExecutionRequest(
            fixture_id,
            fixture["function_name"],
            fixture["arguments"],
            ExecutionType.LOCAL_EXECUTABLE,
        ))
        assert result.status == ExecutionStatus.PASSED
        assert result.data == fixture["result"]


def test_every_mock_default_fixture_executes_exactly() -> None:
    tools = proposal_registry()
    fixture_ids = [
        fixture_id
        for tool in tools.records
        if tool["execution"]["default_type"] == "mock"
        for fixture_id in tool["execution"]["fixture_ids"]
    ]
    engine = ExecutionEngine(tools, ExecutionRouter([MockAdapter.from_registry(tools, fixture_ids)]))
    for fixture_id in fixture_ids:
        fixture = tools.load_fixture(fixture_id)
        result = engine.execute(ExecutionRequest(
            fixture_id,
            fixture["function_name"],
            fixture["arguments"],
            ExecutionType.MOCK,
        ))
        assert result.status == ExecutionStatus.PASSED
        assert result.data == fixture["result"]


def test_local_calculator_rejects_code_and_unbounded_power() -> None:
    tools = proposal_registry()
    engine = ExecutionEngine(tools, ExecutionRouter([LocalExecutableAdapter()]))
    for expression in ("__import__('os')", "2 ** 100"):
        result = engine.execute(ExecutionRequest(
            "unsafe",
            "calculator_evaluate",
            {"expression": expression},
            ExecutionType.LOCAL_EXECUTABLE,
        ))
        assert result.status == ExecutionStatus.FAILED


def test_timezone_reports_ambiguity_and_rejects_nonexistent_time() -> None:
    tools = proposal_registry()
    engine = ExecutionEngine(tools, ExecutionRouter([LocalExecutableAdapter()]))
    ambiguous = engine.execute(ExecutionRequest(
        "ambiguous",
        "time_convert_timezone",
        {
            "local_datetime": "2026-10-25T01:30:00",
            "source_timezone": "Europe/London",
            "target_timezone": "Europe/Istanbul",
        },
        ExecutionType.LOCAL_EXECUTABLE,
    ))
    assert ambiguous.status == ExecutionStatus.PASSED
    assert ambiguous.data["ambiguous"] is True

    nonexistent = engine.execute(ExecutionRequest(
        "nonexistent",
        "time_convert_timezone",
        {
            "local_datetime": "2026-03-29T01:30:00",
            "source_timezone": "Europe/London",
            "target_timezone": "Europe/Istanbul",
        },
        ExecutionType.LOCAL_EXECUTABLE,
    ))
    assert nonexistent.status == ExecutionStatus.FAILED
    assert nonexistent.error == "nonexistent_local_datetime"


def test_holiday_distinguishes_half_day_and_rejects_unknown_year() -> None:
    tools = proposal_registry()
    engine = ExecutionEngine(tools, ExecutionRouter([LocalExecutableAdapter()]))
    half_day = engine.execute(ExecutionRequest(
        "half-day",
        "holiday_is_business_day",
        {"date": "2026-10-28"},
        ExecutionType.LOCAL_EXECUTABLE,
    ))
    assert half_day.status == ExecutionStatus.PASSED
    assert half_day.data["day_status"] == "half_day_holiday"
    assert half_day.data["is_full_business_day"] is False

    unsupported = engine.execute(ExecutionRequest(
        "unsupported-year",
        "holiday_is_business_day",
        {"date": "2027-01-01"},
        ExecutionType.LOCAL_EXECUTABLE,
    ))
    assert unsupported.status == ExecutionStatus.FAILED
    assert unsupported.error == "unsupported_holiday_year"


def test_synthetic_calendar_requires_confirmation_and_resets() -> None:
    tools = proposal_registry()
    adapter = StatefulSimulationAdapter()
    engine = ExecutionEngine(tools, ExecutionRouter([adapter]))
    list_fixture = tools.load_fixture("calendar.synthetic.seed")
    seeded = engine.execute(ExecutionRequest(
        "seeded",
        list_fixture["function_name"],
        list_fixture["arguments"],
        ExecutionType.FULLY_SIMULATED,
    ))
    assert seeded.status == ExecutionStatus.PASSED
    assert seeded.data == list_fixture["result"]

    create_arguments = {
        "title": "Pilot sonuçlarını değerlendir",
        "start_datetime": "2026-08-12T14:00:00+03:00",
        "end_datetime": "2026-08-12T14:30:00+03:00",
        "confirmed": False,
    }
    unconfirmed = engine.execute(ExecutionRequest(
        "unconfirmed",
        "calendar_create_event",
        create_arguments,
        ExecutionType.FULLY_SIMULATED,
    ))
    assert unconfirmed.status == ExecutionStatus.PASSED
    assert unconfirmed.data == {"event_id": None, "status": "confirmation_required"}

    create_arguments["confirmed"] = True
    created = engine.execute(ExecutionRequest(
        "confirmed",
        "calendar_create_event",
        create_arguments,
        ExecutionType.FULLY_SIMULATED,
    ))
    assert created.status == ExecutionStatus.PASSED
    assert created.data == {"event_id": "EVT-CALENDAR-002", "status": "created"}

    listed = engine.execute(ExecutionRequest(
        "list",
        "calendar_list_events",
        {
            "start_datetime": "2026-08-12T00:00:00+03:00",
            "end_datetime": "2026-08-13T00:00:00+03:00",
        },
        ExecutionType.FULLY_SIMULATED,
    ))
    assert [event["event_id"] for event in listed.data["events"]] == ["EVT-CALENDAR-002"]

    adapter.reset()
    listed_after_reset = engine.execute(ExecutionRequest(
        "list-reset",
        "calendar_list_events",
        {
            "start_datetime": "2026-08-12T00:00:00+03:00",
            "end_datetime": "2026-08-13T00:00:00+03:00",
        },
        ExecutionType.FULLY_SIMULATED,
    ))
    assert listed_after_reset.data == {"events": []}
