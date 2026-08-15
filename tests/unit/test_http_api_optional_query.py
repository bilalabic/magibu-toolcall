"""Reference example: testing a `real_api` tool offline with an injected transport.

Contributors can copy this module as a starting point. The key idea is that
``HttpJsonAdapter`` accepts any object implementing the ``JsonTransport``
protocol, so a real_api tool can be exercised end to end without ever touching
the network: the fake transport records the URL and headers the adapter built
and returns a canned JSON response.

It also pins the optional-query-parameter contract: a parameter declared in
``execution.http.query_map`` but omitted from a call must not appear in the
query string, while an argument that has no ``query_map`` entry is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from tool_call_tr.execution import (
    ExecutionEngine,
    ExecutionRequest,
    ExecutionRouter,
    ExecutionStatus,
    ExecutionType,
    HttpJsonAdapter,
)
from tool_call_tr.network import JsonHttpResponse
from tool_call_tr.registry import ToolRegistry
from tool_call_tr.schemas import SchemaStore


ROOT = Path(__file__).resolve().parents[2]


class RecordingTransport:
    """A ``JsonTransport`` stand-in that answers from memory and records the call."""

    def __init__(self, response: JsonHttpResponse) -> None:
        self.response = response
        self.request: dict[str, Any] | None = None

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.request = {
            "method": method,
            "url": url,
            "headers": dict(headers),
            "body": body,
            "timeout": timeout_seconds,
        }
        return self.response


def station_tool(lifecycle: str = "candidate") -> dict[str, Any]:
    """A real_api tool whose ``station_id`` parameter is an optional filter.

    ``station_id`` is declared in ``function.parameters.properties`` and in
    ``execution.http.query_map``, but it is deliberately absent from
    ``function.parameters.required`` — that is what makes it optional.
    """

    return {
        "tool_registry_version": "0.1.0",
        "tool_id": "weather.get_station_reading.v1",
        "tool_version": "1.0.0",
        "domain": "weather",
        "function": {
            "name": "weather_get_station_reading",
            "description": "Bir ildeki hava istasyonu ölçümlerini getirir; istasyon filtresi isteğe bağlıdır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "İl adı."},
                    "station_id": {"type": "string", "description": "İstasyon kimliği (isteğe bağlı filtre)."},
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {"readings": {"type": "array", "items": {"type": "object"}}},
            "required": ["readings"],
            "additionalProperties": False,
        },
        "execution": {
            "default_type": "real_api",
            "supported_types": ["real_api"],
            "fixture_ids": [],
            "resettable": False,
            "http": {
                "method": "GET",
                "url": "https://api.example.tr/v1/readings",
                "allowed_hosts": ["api.example.tr"],
                "query_map": {"city": "city", "station_id": "station"},
                "headers": {"X-Client": "magibu-toolcall"},
                "authentication": {
                    "type": "header",
                    "env_var": "EXAMPLE_TR_API_KEY",
                    "header": "X-API-Key",
                    "prefix": "",
                },
                "response_path": ["data"],
                "timeout_ms": 5000,
            },
        },
        "access": {
            "source": "official_candidate",
            "url": "https://api.example.tr/v1/readings",
            "authentication": "api_key",
            "credential_env_vars": ["EXAMPLE_TR_API_KEY"],
            "license": "terms-reviewed-separately",
            "license_url": "https://api.example.tr/terms",
            "terms_checked_on": "2026-08-06",
        },
        "risks": {
            "safety": "low",
            "freshness": "volatile",
            "personal_data": False,
            "side_effects": False,
            "notes": "Salt okunur ölçüm listeleme.",
        },
        "lifecycle": lifecycle,
    }


def build(tool: dict[str, Any]) -> tuple[ExecutionEngine, RecordingTransport]:
    registry = ToolRegistry([tool])
    transport = RecordingTransport(JsonHttpResponse(200, {"data": {"readings": [{"station_id": "S-1"}]}}, {}))
    adapter = HttpJsonAdapter(registry, transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret"})
    return ExecutionEngine(registry, ExecutionRouter([adapter])), transport


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_optional_parameter_tool_matches_the_registry_schema() -> None:
    SchemaStore(ROOT / "schemas").validate("registry", station_tool())


def test_omitted_optional_parameter_is_absent_from_the_query_string() -> None:
    engine, transport = build(station_tool())
    result = engine.execute(
        ExecutionRequest("call_001", "weather_get_station_reading", {"city": "Ankara"}, ExecutionType.REAL_API)
    )
    assert result.status == ExecutionStatus.PASSED
    assert transport.request is not None
    assert query_of(transport.request["url"]) == {"city": ["Ankara"]}
    assert "station" not in transport.request["url"]


def test_supplied_optional_parameter_is_mapped_deterministically() -> None:
    engine, transport = build(station_tool())
    result = engine.execute(
        ExecutionRequest(
            "call_001",
            "weather_get_station_reading",
            {"city": "Ankara", "station_id": "S-42"},
            ExecutionType.REAL_API,
        )
    )
    assert result.status == ExecutionStatus.PASSED
    assert transport.request is not None
    # Arguments are emitted in sorted order, so the URL is stable across runs.
    assert transport.request["url"] == "https://api.example.tr/v1/readings?city=Ankara&station=S-42"


def test_argument_without_a_query_map_entry_is_rejected_before_transport() -> None:
    tool = station_tool()
    # The parameter schema accepts it, but the HTTP contract does not map it.
    tool["function"]["parameters"]["properties"]["sensor_id"] = {"type": "string"}
    registry = ToolRegistry([tool])
    transport = RecordingTransport(JsonHttpResponse(200, {"data": {"readings": []}}, {}))
    adapter = HttpJsonAdapter(registry, transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret"})
    result = adapter.execute(
        ExecutionRequest(
            "call_001",
            "weather_get_station_reading",
            {"city": "Ankara", "sensor_id": "S-9"},
            ExecutionType.REAL_API,
        )
    )
    assert result.status == ExecutionStatus.FAILED
    assert result.error == "http_argument_not_mapped"
    assert transport.request is None


def test_missing_required_parameter_fails_schema_validation_before_the_adapter() -> None:
    engine, transport = build(station_tool())
    with pytest.raises(JsonSchemaValidationError):
        engine.execute(
            ExecutionRequest("call_001", "weather_get_station_reading", {"station_id": "S-42"}, ExecutionType.REAL_API)
        )
    assert transport.request is None


def test_optional_parameters_do_not_relax_https_and_host_restrictions() -> None:
    plain_http = station_tool()
    plain_http["execution"]["http"]["url"] = "http://api.example.tr/v1/readings"
    foreign_host = station_tool()
    foreign_host["execution"]["http"]["url"] = "https://other.example.tr/v1/readings"
    for tool, expected in ((plain_http, "http_endpoint_not_allowed"), (foreign_host, "http_host_not_allowed")):
        registry = ToolRegistry([tool])
        transport = RecordingTransport(JsonHttpResponse(200, {"data": {"readings": []}}, {}))
        adapter = HttpJsonAdapter(registry, transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret"})
        result = adapter.execute(
            ExecutionRequest("call_001", "weather_get_station_reading", {"city": "Ankara"}, ExecutionType.REAL_API)
        )
        assert result.status == ExecutionStatus.FAILED
        assert result.error == expected
        assert transport.request is None


def test_credentials_never_reach_the_serialized_result() -> None:
    engine, transport = build(station_tool())
    result = engine.execute(
        ExecutionRequest("call_001", "weather_get_station_reading", {"city": "Ankara"}, ExecutionType.REAL_API)
    )
    assert transport.request is not None
    assert transport.request["headers"]["X-API-Key"] == "secret"
    assert "secret" not in json.dumps(result.to_dict(), ensure_ascii=False)
