"""CLI contract for `tool run-api`: registry selection and candidate gating."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tool_call_tr import cli
from tool_call_tr.cli import main
from tool_call_tr.network import JsonHttpResponse

from test_http_api_optional_query import RecordingTransport, station_tool


def write_registry(directory: Path, tool: dict[str, Any]) -> Path:
    path = directory / "registry.jsonl"
    path.write_text(json.dumps(tool, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def offline_adapter(monkeypatch: pytest.MonkeyPatch) -> RecordingTransport:
    """Keep `tool run-api` off the network while exercising the CLI gates."""

    transport = RecordingTransport(JsonHttpResponse(200, {"data": {"readings": [{"station_id": "S-1"}]}}, {}))
    original = cli.HttpJsonAdapter
    monkeypatch.setattr(
        cli,
        "HttpJsonAdapter",
        lambda registry: original(registry, transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret"}),
    )
    return transport


def test_run_api_requires_live_confirmation(tmp_path: Path, capsys) -> None:
    path = write_registry(tmp_path, station_tool("approved"))
    exit_code = main([
        "tool", "run-api", "weather_get_station_reading",
        "--arguments", '{"city": "Ankara"}',
        "--registry", str(path),
        "--allow-candidate",
    ])
    assert exit_code == 1
    assert "--confirm-live is required" in capsys.readouterr().out


def test_run_api_rejects_candidate_tool_without_the_explicit_flag(
    tmp_path: Path, capsys, offline_adapter: RecordingTransport
) -> None:
    path = write_registry(tmp_path, station_tool("candidate"))
    exit_code = main([
        "tool", "run-api", "weather_get_station_reading",
        "--arguments", '{"city": "Ankara"}',
        "--registry", str(path),
        "--confirm-live",
    ])
    assert exit_code == 1
    assert "ERROR LIVE_EXECUTION_BLOCKED: live execution requires an approved registry tool" in capsys.readouterr().out
    assert offline_adapter.request is None


def test_run_api_runs_candidate_tool_with_both_confirmations(
    tmp_path: Path, capsys, offline_adapter: RecordingTransport
) -> None:
    path = write_registry(tmp_path, station_tool("candidate"))
    exit_code = main([
        "tool", "run-api", "weather_get_station_reading",
        "--arguments", '{"city": "Ankara"}',
        "--registry", str(path),
        "--confirm-live",
        "--allow-candidate",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["data"] == {"readings": [{"station_id": "S-1"}]}
    assert offline_adapter.request is not None
    assert offline_adapter.request["url"] == "https://api.example.tr/v1/readings?city=Ankara"


def test_run_api_still_rejects_non_candidate_lifecycles_with_the_flag(
    tmp_path: Path, capsys, offline_adapter: RecordingTransport
) -> None:
    path = write_registry(tmp_path, station_tool("demo"))
    exit_code = main([
        "tool", "run-api", "weather_get_station_reading",
        "--arguments", '{"city": "Ankara"}',
        "--registry", str(path),
        "--confirm-live",
        "--allow-candidate",
    ])
    assert exit_code == 1
    assert "LIVE_EXECUTION_BLOCKED" in capsys.readouterr().out
    assert offline_adapter.request is None
