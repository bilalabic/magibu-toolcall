from __future__ import annotations

import pytest

from tool_call_tr.cli import main
from tool_call_tr.ids import (
    ContributorRange,
    IdError,
    assert_stable_after_acceptance,
    generate_call_id,
    generate_record_id,
    validate_record_id,
)
from tool_call_tr.versioning import (
    SemanticVersion,
    VersionError,
    require_development_version,
    validate_tool_id_major,
    version_target_for,
)


@pytest.mark.parametrize(
    ("kind", "source_type", "expected"),
    [
        ("dataset", "translated", "tctr_tr_000001"),
        ("dataset", "original_turkish", "tctr_ot_000001"),
        ("dataset", "turkey_native", "tctr_tn_000001"),
        ("benchmark", "translated", "bench_tr_000001"),
        ("benchmark", "original_turkish", "bench_ot_000001"),
        ("benchmark", "turkey_native", "bench_tn_000001"),
    ],
)
def test_record_id_generation(kind: str, source_type: str, expected: str) -> None:
    assert generate_record_id(kind, source_type, 1) == expected
    assert validate_record_id(expected, kind=kind, source_type=source_type)


def test_collision_range_and_stability_rules() -> None:
    with pytest.raises(IdError, match="collision"):
        generate_record_id("dataset", "translated", 1, existing={"tctr_tr_000001"})
    with pytest.raises(IdError, match="outside"):
        generate_record_id("dataset", "translated", 9, contributor_range=ContributorRange(10, 20))
    with pytest.raises(IdError, match="immutable"):
        assert_stable_after_acceptance("tctr_tr_000001", "tctr_tr_000002", "accepted")


def test_tool_call_id_generation_and_collision() -> None:
    assert generate_call_id(1) == "call_001"
    assert generate_call_id(1000) == "call_1000"
    with pytest.raises(IdError, match="collision"):
        generate_call_id(2, existing={"call_002"})


@pytest.mark.parametrize("value", ["0.1.0", "1.2.3", "2.0.0-rc.1+build.5"])
def test_semantic_version_validation(value: str) -> None:
    assert SemanticVersion.parse(value).major == int(value.split(".", 1)[0])


@pytest.mark.parametrize("value", ["01.0.0", "1", "v1.0.0", "1.0"])
def test_invalid_semantic_versions(value: str) -> None:
    with pytest.raises(VersionError):
        SemanticVersion.parse(value)


def test_development_and_tool_major_rules() -> None:
    assert require_development_version("0.1.0").is_development
    with pytest.raises(VersionError, match="0.x"):
        require_development_version("1.0.0")
    assert validate_tool_id_major("weather.get_forecast.v1", "1.2.0")
    assert not validate_tool_id_major("weather.get_forecast.v1", "2.0.0")
    assert version_target_for("tool_added") == "tool_registry_version"


def test_generate_id_cli(capsys) -> None:
    assert main(["dataset", "generate-id", "42", "--source-type", "turkey_native"]) == 0
    assert capsys.readouterr().out.strip() == "tctr_tn_000042"
