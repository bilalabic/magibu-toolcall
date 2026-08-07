from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tool_call_tr.execution import ExecutionEngine, ExecutionRequest, ExecutionRouter, ExecutionStatus, ExecutionType, HttpJsonAdapter
from tool_call_tr.network import JsonHttpResponse, NetworkTimeout
from tool_call_tr.registry import RegistryValidationError, ToolRegistry
from tool_call_tr.schemas import SchemaStore


ROOT = Path(__file__).resolve().parents[2]


class FakeTransport:
    def __init__(self, response: JsonHttpResponse | Exception) -> None:
        self.response = response
        self.request: dict[str, Any] | None = None

    def request_json(
        self, *, method: str, url: str, headers: Mapping[str, str], body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.request = {"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout_seconds}
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def api_tool() -> dict:
    value = json.loads((ROOT / "tests" / "fixtures" / "registry" / "valid_tool.json").read_text(encoding="utf-8"))
    value["execution"] = {
        "default_type": "real_api",
        "supported_types": ["real_api"],
        "fixture_ids": [],
        "resettable": False,
        "http": {
            "method": "GET",
            "url": "https://api.example.tr/v1/add",
            "allowed_hosts": ["api.example.tr"],
            "query_map": {"left": "sol", "right": "sag"},
            "headers": {"X-Client": "magibu-toolcall"},
            "authentication": {"type": "header", "env_var": "EXAMPLE_TR_API_KEY", "header": "X-API-Key", "prefix": ""},
            "response_path": ["data"],
            "timeout_ms": 5000,
        },
    }
    value["access"] = {
        "source": "official_candidate",
        "url": "https://api.example.tr/v1/add",
        "authentication": "api_key",
        "credential_env_vars": ["EXAMPLE_TR_API_KEY"],
        "license": "terms-reviewed-separately",
        "license_url": "https://api.example.tr/terms",
        "terms_checked_on": "2026-08-06",
    }
    value["lifecycle"] = "candidate"
    return value


def test_registry_real_api_contract_is_machine_validated(tmp_path: Path) -> None:
    record = api_tool()
    SchemaStore(ROOT / "schemas").validate("registry", record)
    path = tmp_path / "registry.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    assert ToolRegistry.load(path).by_function_name("utility_add")["execution"]["http"]["method"] == "GET"

    invalid = copy.deepcopy(record)
    invalid["execution"].pop("http")
    path.write_text(json.dumps(invalid, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(RegistryValidationError) as raised:
        ToolRegistry.load(path)
    assert any(issue.code == "REAL_API_HTTP_REQUIRED" for issue in raised.value.issues)


def test_https_adapter_maps_query_auth_and_response_without_leaking_secret() -> None:
    registry = ToolRegistry([api_tool()])
    transport = FakeTransport(JsonHttpResponse(200, {"data": {"result": 5}}, {}))
    adapter = HttpJsonAdapter(registry, transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret-value"})
    engine = ExecutionEngine(registry, ExecutionRouter([adapter]))
    result = engine.execute(ExecutionRequest("call_001", "utility_add", {"left": 2, "right": 3}, ExecutionType.REAL_API))
    assert result.status == ExecutionStatus.PASSED
    assert result.data == {"result": 5}
    assert transport.request is not None
    assert transport.request["method"] == "GET"
    assert transport.request["url"] == "https://api.example.tr/v1/add?sol=2&sag=3"
    assert transport.request["headers"]["X-API-Key"] == "secret-value"
    assert "secret-value" not in json.dumps(result.to_dict())


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (JsonHttpResponse(429, {"private": "ignored"}, {}), ExecutionStatus.RATE_LIMITED),
        (JsonHttpResponse(500, {"private": "ignored"}, {}), ExecutionStatus.FAILED),
        (JsonHttpResponse(200, {}, {}), ExecutionStatus.EMPTY_RESULT),
        (JsonHttpResponse(200, {"wrong": {}}, {}), ExecutionStatus.INVALID_RESULT),
        (NetworkTimeout("timeout"), ExecutionStatus.TIMEOUT),
    ],
)
def test_https_adapter_normalizes_operational_statuses(response, expected) -> None:
    registry = ToolRegistry([api_tool()])
    adapter = HttpJsonAdapter(registry, transport=FakeTransport(response), environment={"EXAMPLE_TR_API_KEY": "secret"})
    result = adapter.execute(ExecutionRequest("call_001", "utility_add", {"left": 2, "right": 3}, ExecutionType.REAL_API))
    assert result.status == expected
    assert "ignored" not in (result.error or "")


def test_https_adapter_rejects_unallowlisted_host_before_transport() -> None:
    tool = api_tool()
    tool["execution"]["http"]["allowed_hosts"] = ["different.example.tr"]
    transport = FakeTransport(JsonHttpResponse(200, {"data": {"result": 5}}, {}))
    adapter = HttpJsonAdapter(ToolRegistry([tool]), transport=transport, environment={"EXAMPLE_TR_API_KEY": "secret"})
    result = adapter.execute(ExecutionRequest("call_001", "utility_add", {"left": 2, "right": 3}, ExecutionType.REAL_API))
    assert result.status == ExecutionStatus.FAILED
    assert result.error == "http_host_not_allowed"
    assert transport.request is None
