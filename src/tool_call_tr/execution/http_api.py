"""Manifest-driven, HTTPS-only, read-only JSON API execution adapter."""

from __future__ import annotations

import os
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tool_call_tr.execution.core import ExecutionRequest, ExecutionResult, ExecutionStatus, ExecutionType
from tool_call_tr.network import JsonTransport, NetworkError, NetworkTimeout, UrllibJsonTransport
from tool_call_tr.registry import ToolRegistry


class HttpJsonAdapter:
    execution_type = ExecutionType.REAL_API

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        transport: JsonTransport | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.registry = registry
        self.transport = transport or UrllibJsonTransport()
        self.environment = environment if environment is not None else os.environ

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.execution_type != self.execution_type:
            raise ValueError("request execution type does not match real API adapter")
        tool = self.registry.by_function_name(request.function_name)
        contract = tool["execution"].get("http")
        if contract is None:
            return self._result(request, ExecutionStatus.FAILED, error="http_contract_missing")
        try:
            url = self._build_url(contract, request.arguments)
            headers = self._build_headers(contract)
        except ValueError as exc:
            return self._result(request, ExecutionStatus.FAILED, error=str(exc))
        timeout_ms = request.timeout_ms or contract["timeout_ms"]
        try:
            response = self.transport.request_json(
                method="GET",
                url=url,
                headers=headers,
                body=None,
                timeout_seconds=timeout_ms / 1000,
            )
        except NetworkTimeout:
            return self._result(request, ExecutionStatus.TIMEOUT, error="http_timeout")
        except NetworkError:
            return self._result(request, ExecutionStatus.FAILED, error="http_network_error")
        if response.status_code == 429:
            return self._result(request, ExecutionStatus.RATE_LIMITED, error="http_429")
        if response.status_code < 200 or response.status_code >= 300:
            return self._result(request, ExecutionStatus.FAILED, error=f"http_{response.status_code}")
        if response.body is None or response.body == {} or response.body == []:
            return self._result(request, ExecutionStatus.EMPTY_RESULT)
        try:
            data = _extract_path(response.body, contract["response_path"])
        except (KeyError, IndexError, TypeError):
            return self._result(request, ExecutionStatus.INVALID_RESULT, error="response_path_not_found")
        return self._result(request, ExecutionStatus.PASSED, data=data)

    def _build_url(self, contract: dict[str, Any], arguments: dict[str, Any]) -> str:
        parsed = urlsplit(contract["url"])
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("http_endpoint_not_allowed")
        if parsed.hostname not in set(contract["allowed_hosts"]):
            raise ValueError("http_host_not_allowed")
        mapping = contract["query_map"]
        # Required arguments are already enforced by the registry parameter schema in
        # ExecutionEngine.execute; here only declared arguments may reach the query string,
        # and omitted (optional) ones are simply left out.
        if not set(arguments) <= set(mapping):
            raise ValueError("http_argument_not_mapped")
        query = list(parse_qsl(parsed.query, keep_blank_values=True))
        query.extend((mapping[name], _query_value(arguments[name])) for name in sorted(arguments))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def _build_headers(self, contract: dict[str, Any]) -> dict[str, str]:
        headers = {"Accept": "application/json", **contract["headers"]}
        auth = contract["authentication"]
        if auth["type"] == "none":
            return headers
        credential = self.environment.get(auth["env_var"])
        if not credential:
            raise ValueError("http_credential_not_configured")
        headers[auth["header"]] = f"{auth['prefix']}{credential}"
        return headers

    @staticmethod
    def _result(
        request: ExecutionRequest,
        status: ExecutionStatus,
        *,
        data: Any = None,
        error: str | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(request.call_id, request.function_name, ExecutionType.REAL_API, status, data=data, error=error)

    def reset(self) -> None:
        return None


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        raise ValueError("http_complex_query_value_not_supported")
    return str(value)


def _extract_path(value: Any, path: list[str | int]) -> Any:
    current = value
    for segment in path:
        current = current[segment]
    return current
