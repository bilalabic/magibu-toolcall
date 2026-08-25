"""Smoke and boundary tests for the Paket 9 local TÜİK population tools."""

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
    LocalExecutableAdapter,
)
from tool_call_tr.execution.local import demography_tuik as pop
from tool_call_tr.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registry" / "proposals" / "demography_tuik.jsonl"
BLUEPRINT_PATH = ROOT / "blueprints" / "demography_tuik.jsonl"
SNAPSHOT_ROOT = ROOT / "data" / "snapshots" / "tuik" / "population" / "v1"


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


def test_registry_has_exactly_two_population_tools() -> None:
    loaded = registry()

    assert len(loaded.records) == 2
    for tool_id in (
        "demography.get_population.v1",
        "demography.compare_population.v1",
    ):
        tool = loaded.by_tool_id(tool_id)
        assert tool["execution"]["default_type"] == "local_executable"
        assert tool["execution"]["supported_types"] == ["local_executable"]
        assert tool["access"]["authentication"] == "none"


def test_snapshot_covers_five_provinces_two_years() -> None:
    import csv

    with (SNAPSHOT_ROOT / "population_2023_2024.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 10
    assert {row["province"] for row in rows} == {
        "İstanbul",
        "Ankara",
        "İzmir",
        "Bursa",
        "Antalya",
    }
    assert {int(row["year"]) for row in rows} == {2023, 2024}


def test_get_population_smoke_happy_path() -> None:
    result = execute(
        "demography_get_population",
        {"province": "İzmir", "year": 2023},
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["province"] == "İzmir"
    assert result.data["year"] == 2023
    assert result.data["population"] == 4479525
    assert result.data["source"]["provider"] == "TÜİK"


def test_source_object_carries_all_six_agreed_fields() -> None:
    provenance = json.loads((SNAPSHOT_ROOT / "provenance.json").read_text(encoding="utf-8"))
    entry = provenance["sources"][0]
    expected = {
        "provider": provenance["provider"],
        "dataset": provenance["source_name"],
        "release_id": entry["release_id"],
        "source_url": entry["source_url"],
        "snapshot_version": provenance["snapshot_version"],
        "retrieved_at": provenance["retrieved_at"],
    }

    for function_name, arguments in (
        ("demography_get_population", {"province": "İzmir", "year": 2023}),
        (
            "demography_compare_population",
            {"province_a": "Ankara", "province_b": "Bursa", "year": 2024},
        ),
        (
            "demography_compare_population",
            {"province": "İstanbul", "year_a": 2024, "year_b": 2023},
        ),
    ):
        result = execute(function_name, arguments)
        assert result.status == ExecutionStatus.PASSED
        assert result.data["source"] == expected


def test_transformation_notes_name_the_conversion_script() -> None:
    provenance = json.loads((SNAPSHOT_ROOT / "provenance.json").read_text(encoding="utf-8"))

    assert any(
        "scripts/snapshots/demography_tuik.py" in note
        for note in provenance["transformation_notes"]
    )


@pytest.mark.parametrize(
    ("queried", "expected_province"),
    (
        ("ankara", "Ankara"),
        ("ANKARA", "Ankara"),
        ("İSTANBUL", "İstanbul"),
        ("istanbul", "İstanbul"),
        ("  izmir  ", "İzmir"),
    ),
)
def test_get_population_tolerates_turkish_letter_forms(
    queried: str,
    expected_province: str,
) -> None:
    result = execute("demography_get_population", {"province": queried, "year": 2024})

    assert result.status == ExecutionStatus.PASSED
    assert result.data["province"] == expected_province


def test_compare_population_returns_snapshot_spelling_in_both_modes() -> None:
    province_mode = execute(
        "demography_compare_population",
        {"province_a": "ankara", "province_b": "BURSA", "year": 2024},
    )
    assert province_mode.status == ExecutionStatus.PASSED
    assert province_mode.data["comparison"]["province_a"] == "Ankara"
    assert province_mode.data["comparison"]["province_b"] == "Bursa"

    year_mode = execute(
        "demography_compare_population",
        {"province": "İSTANBUL", "year_a": 2024, "year_b": 2023},
    )
    assert year_mode.status == ExecutionStatus.PASSED
    assert year_mode.data["comparison"]["province"] == "İstanbul"


def test_compare_population_province_vs_province_happy_path() -> None:
    result = execute(
        "demography_compare_population",
        {"province_a": "Ankara", "province_b": "Bursa", "year": 2024},
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["difference"] == 5864049 - 3238618
    assert result.data["comparison"]["province_a"] == "Ankara"
    assert result.data["comparison"]["province_b"] == "Bursa"


def test_compare_population_year_vs_year_happy_path() -> None:
    result = execute(
        "demography_compare_population",
        {"province": "İstanbul", "year_a": 2024, "year_b": 2023},
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.data["difference"] == 15701602 - 15655924
    assert result.data["comparison"]["province"] == "İstanbul"


@pytest.mark.parametrize(
    ("function_name", "arguments"),
    (
        ("demography_get_population", {"year": 2024}),
        ("demography_get_population", {"province": "Ankara"}),
        ("demography_get_population", {"province": "Ankara", "year": "2024"}),
         ),
)
def test_schema_rejects_missing_or_invalid_arguments(
    function_name: str,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        execute(function_name, arguments)


def test_get_population_out_of_snapshot_year_fails_cleanly() -> None:
    result = execute(
        "demography_get_population",
        {"province": "İstanbul", "year": 1990},
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("lookup_error:")


def test_get_population_unknown_province_fails_cleanly() -> None:
    result = execute(
        "demography_get_population",
        {"province": "Bilinmeyen İl", "year": 2024},
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None and result.error.startswith("lookup_error:")


@pytest.mark.parametrize(
    "arguments",
    (
        pytest.param({}, id="empty"),
        pytest.param({"province": "Ankara"}, id="partial_year_mode"),
        pytest.param(
            {"province_a": "Ankara", "province_b": "Bursa", "year": 2024, "year_a": 2023},
            id="mixed_modes",
        ),
        pytest.param(
            {"province": "Ankara", "province_b": "Bursa", "year_a": 2023, "year_b": 2024},
            id="year_mode_plus_stray_province_b",
        ),
    ),
)
def test_compare_population_rejects_anything_but_one_whole_mode(
    arguments: dict[str, object],
) -> None:
    """Neither mode is satisfied unless exactly its three fields are supplied.

    The two argument sets are declared as `oneOf` branches, so a mixed call such
    as `{province_a, province_b, year, year_a}` is refused by the parameter schema
    before the tool runs — the model sees the boundary instead of discovering it
    from a failed call.
    """

    with pytest.raises(ValidationError):
        execute("demography_compare_population", arguments)


def test_compare_population_guards_its_modes_without_the_schema() -> None:
    """The executor refuses a mixed call on its own, not only through the schema."""

    with pytest.raises(ValueError, match="^input_error:"):
        pop.demography_compare_population(
            {"province_a": "Ankara", "province_b": "Bursa", "year": 2024, "year_a": 2023}
        )


def test_local_population_executors_do_not_open_network_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    def forbidden_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("local population executor attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden_connection)

    assert execute(
        "demography_get_population", {"province": "Antalya", "year": 2024}
    ).status == ExecutionStatus.PASSED
    assert execute(
        "demography_compare_population",
        {"province_a": "Antalya", "province_b": "Bursa", "year": 2024},
    ).status == ExecutionStatus.PASSED


def test_normalizer_folds_turkish_letter_forms() -> None:
    assert pop._normalized_turkish("İSTANBUL") == pop._normalized_turkish("İstanbul")
    assert pop._normalized_turkish(" ankara ") == pop._normalized_turkish("Ankara")
    assert pop._normalized_turkish("Ankara") != pop._normalized_turkish("Bursa")


def test_module_keeps_no_snapshot_cache() -> None:
    """Each call re-reads the ten-row snapshot; a module global would go stale."""

    assert not hasattr(pop, "_CACHE")


def test_repeated_calls_are_deterministic() -> None:
    first = execute("demography_get_population", {"province": "Bursa", "year": 2023})
    second = execute("demography_get_population", {"province": "Bursa", "year": 2023})
    assert first.data == second.data