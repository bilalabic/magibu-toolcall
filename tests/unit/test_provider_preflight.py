from __future__ import annotations

from typing import Any, Mapping

from tool_call_tr.cli import main
from tool_call_tr.config import Settings
from tool_call_tr.network import JsonHttpResponse
from tool_call_tr.provider_preflight import check_provider_models


class FakeTransport:
    def __init__(self, responses: list[JsonHttpResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        return self.responses.pop(0)


def configured_settings(tmp_path) -> Settings:
    return Settings(
        project_root=tmp_path,
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        openai_api_key="openai-secret",
        openai_model="gpt-primary",
        openai_escalation_model="gpt-escalation",
        openai_embedding_model="embedding-model",
    )


def test_preflight_checks_expected_models_without_generation_or_secret_output(tmp_path) -> None:
    transport = FakeTransport([
        JsonHttpResponse(200, {"data": [
            {"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"},
        ]}, {}),
        JsonHttpResponse(200, {"data": [
            {"id": "gpt-primary"}, {"id": "gpt-escalation"}, {"id": "embedding-model"},
        ]}, {}),
    ])
    results = check_provider_models(configured_settings(tmp_path), transport=transport)
    assert all(result.ok for result in results)
    assert [request["method"] for request in transport.requests] == ["GET", "GET"]
    assert all(request["body"] is None for request in transport.requests)
    assert transport.requests[0]["url"] == "https://api.deepseek.com/models"
    assert transport.requests[1]["url"] == "https://api.openai.com/v1/models"
    assert "deepseek-secret" not in str([result.to_dict() for result in results])
    assert "openai-secret" not in str([result.to_dict() for result in results])


def test_preflight_reports_missing_model_without_echoing_provider_body(tmp_path) -> None:
    transport = FakeTransport([
        JsonHttpResponse(200, {"data": [{"id": "deepseek-v4-flash"}]}, {}),
    ])
    result = check_provider_models(
        configured_settings(tmp_path), providers=("deepseek",), transport=transport,
    )[0]
    assert not result.ok
    assert result.status == "ok"
    assert [item.model for item in result.models if not item.available] == ["deepseek-v4-pro"]


def test_provider_cli_requires_explicit_live_confirmation(capsys) -> None:
    assert main(["provider", "check"]) == 1
    assert "LIVE_CONFIRMATION_REQUIRED" in capsys.readouterr().out
