from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tool_call_tr.generation.providers import (
    DeepSeekIntegration,
    OpenAIQualityJudge,
    ProviderError,
    ProviderNotConfigured,
    RetryPolicy,
    run_language_plan_with_retry,
)
from tool_call_tr.network import JsonHttpResponse
from tool_call_tr.semantic import CachedEmbeddingSimilarity, OpenAIEmbeddingProvider, cosine_similarity
from tool_call_tr.text_quality import find_internal_operation_markers


ROOT = Path(__file__).resolve().parents[2]


def load_blueprint(name: str) -> dict[str, Any]:
    path = ROOT / "tests" / "fixtures" / "blueprints" / "valid" / name
    return json.loads(path.read_text(encoding="utf-8"))


class FakeTransport:
    def __init__(self, responses: list[JsonHttpResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def request_json(
        self, *, method: str, url: str, headers: Mapping[str, str], body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.requests.append({
            "method": method, "url": url, "headers": dict(headers), "body": body,
            "timeout_seconds": timeout_seconds,
        })
        return self.responses.pop(0)


def test_deepseek_structured_provider_parses_json_and_records_identity() -> None:
    transport = FakeTransport([JsonHttpResponse(200, {
        "id": "deepseek-request-1",
        "model": "deepseek-model-revision",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"ok": True})}}]
    }, {})])
    provider = DeepSeekIntegration("secret", "configured-model", transport=transport)
    response = provider.generate_json(system_prompt="Return JSON.", payload={"input": 1}, role="scenario_generator")
    assert response.value == {"ok": True}
    assert response.identity.provider == "deepseek"
    assert transport.requests[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert transport.requests[0]["body"]["response_format"] == {"type": "json_object"}
    assert transport.requests[0]["body"]["max_tokens"] == 8192
    assert response.usage == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert response.request_id == "deepseek-request-1"
    assert response.identity.model_version == "deepseek-model-revision"


def test_deepseek_language_plan_uses_bounded_non_thinking_json_contract() -> None:
    plan = {
        "user_messages": ["Merhaba"],
        "intermediate_assistant_response": None,
        "final_response": "Merhaba!",
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "model": "deepseek-v4-flash",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
    }, {})])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)
    response = provider.generate_language_plan(load_blueprint("no_tool.json"))
    request = transport.requests[0]["body"]
    assert response.value == plan
    assert request["thinking"] == {"type": "disabled"}
    assert request["max_tokens"] == 1600
    assert "Example JSON output" in request["messages"][0]["content"]
    assert "exactly 1 non-empty" in request["messages"][0]["content"]
    assert "generation_brief" in request["messages"][1]["content"]
    assert '"blueprint"' not in request["messages"][1]["content"]
    assert '"metadata"' not in request["messages"][1]["content"]
    assert not find_internal_operation_markers(request["messages"][0]["content"])
    assert not find_internal_operation_markers(request["messages"][1]["content"])


def test_deepseek_missing_parameter_prompt_keeps_request_in_user_role() -> None:
    plan = {
        "user_messages": ["Hava durumuna bakar mısın?"],
        "intermediate_assistant_response": None,
        "final_response": "Hangi şehir için bakmamı istersiniz?",
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "model": "deepseek-v4-flash",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
    }, {})])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)

    provider.generate_language_plan(load_blueprint("missing_parameter.json"))

    prompt = transport.requests[0]["body"]["messages"][0]["content"]
    assert "user's incomplete request" in prompt
    assert "must not ask the user for the missing value" in prompt
    assert "never as an assistant question" in prompt
    assert '"user_messages":["Hava durumuna bakar mısın?"]' in prompt
    assert '"final_response":"Hangi şehir için bakmamı istersiniz?"' in prompt
    assert '"user_messages":["Ankara için hava nasıl?"]' not in prompt


def test_deepseek_full_record_generation_is_disabled_before_network() -> None:
    transport = FakeTransport([])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)
    with pytest.raises(ProviderError, match="full-record generation") as raised:
        provider.generate_scenario(load_blueprint("no_tool.json"))
    assert not raised.value.retryable
    assert transport.requests == []


def test_deepseek_language_plan_rejects_missing_multi_turn_response() -> None:
    plan = {
        "user_messages": ["Hangi yıl?", "2026-2027"],
        "intermediate_assistant_response": None,
        "final_response": "Takvimi paylaşıyorum.",
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "model": "deepseek-v4-pro",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
    }, {})])
    provider = DeepSeekIntegration("secret", "deepseek-v4-pro", transport=transport)
    with pytest.raises(ProviderError, match="deterministic validation"):
        provider.generate_language_plan(load_blueprint("multi_turn.json"))


def test_deepseek_language_plan_rejects_non_question_clarification() -> None:
    plan = {
        "user_messages": ["Londra'da saat kaç?", "Kaynak dilim Europe/Istanbul."],
        "intermediate_assistant_response": "Kaynak saat dilimini belirttiniz.",
        "final_response": "Londra'da saat 13.00.",
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "model": "deepseek-v4-flash",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
    }, {})])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)
    blueprint = load_blueprint("multi_turn.json")
    if "clarification" not in blueprint["metadata"]["secondary_tags"]:
        blueprint["metadata"]["secondary_tags"].append("clarification")
    with pytest.raises(ProviderError, match="requires an intermediate question"):
        provider.generate_language_plan(blueprint)


def test_deepseek_blocks_unsafe_generation_brief_before_network() -> None:
    transport = FakeTransport([])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)
    blueprint = load_blueprint("no_tool.json")
    blueprint["user_goal"] = "Sentetik kayıt hakkında konuşmak"
    with pytest.raises(ProviderError, match="blocked before request") as raised:
        provider.generate_language_plan(blueprint)
    assert not raised.value.retryable
    assert transport.requests == []


def test_language_plan_retry_uses_clean_repair_instruction() -> None:
    invalid_plan = {
        "user_messages": ["Merhaba"],
        "intermediate_assistant_response": None,
        "final_response": "Bu kayıt sentetiktir.",
    }
    valid_plan = {
        "user_messages": ["Merhaba"],
        "intermediate_assistant_response": None,
        "final_response": "Merhaba! Nasıl yardımcı olabilirim?",
    }
    transport = FakeTransport([
        JsonHttpResponse(200, {
            "model": "deepseek-v4-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(invalid_plan)}}],
        }, {}),
        JsonHttpResponse(200, {
            "model": "deepseek-v4-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(valid_plan)}}],
        }, {}),
    ])
    provider = DeepSeekIntegration("secret", "deepseek-v4-flash", transport=transport)
    response = run_language_plan_with_retry(
        provider,
        load_blueprint("no_tool.json"),
        RetryPolicy(max_attempts=2, base_seconds=0, jitter_ratio=0),
        sleep=lambda _: None,
    )
    assert response.value == valid_plan
    assert response.attempts == 2
    first_prompt = transport.requests[0]["body"]["messages"][0]["content"]
    repair_prompt = transport.requests[1]["body"]["messages"][0]["content"]
    assert "fresh rewrite after a previous response" not in first_prompt
    assert "fresh rewrite after a previous response" in repair_prompt
    assert not find_internal_operation_markers(repair_prompt)


def test_deepseek_errors_never_echo_secret_or_response_body() -> None:
    transport = FakeTransport([JsonHttpResponse(500, {"error": "contains-sensitive-upstream-text"}, {})])
    provider = DeepSeekIntegration("top-secret", "configured-model", transport=transport)
    with pytest.raises(ProviderError) as raised:
        provider.generate_json(system_prompt="Return JSON.", payload={}, role="scenario_generator")
    assert "top-secret" not in str(raised.value)
    assert "contains-sensitive" not in str(raised.value)


def test_provider_errors_classify_retry_and_retry_after_without_exposing_body() -> None:
    limited = DeepSeekIntegration(
        "secret",
        "configured-model",
        transport=FakeTransport([JsonHttpResponse(429, {"error": "hidden"}, {"Retry-After": "2.5"})]),
    )
    with pytest.raises(ProviderError) as limited_error:
        limited.generate_json(system_prompt="Return JSON.", payload={}, role="scenario_generator")
    assert limited_error.value.retryable
    assert limited_error.value.retry_after_seconds == 2.5
    assert limited_error.value.status_code == 429

    invalid = DeepSeekIntegration(
        "secret",
        "configured-model",
        transport=FakeTransport([JsonHttpResponse(400, {"error": "hidden"}, {})]),
    )
    with pytest.raises(ProviderError) as invalid_error:
        invalid.generate_json(system_prompt="Return JSON.", payload={}, role="scenario_generator")
    assert not invalid_error.value.retryable
    assert invalid_error.value.status_code == 400


def test_openai_embedding_provider_batches_and_validates_response() -> None:
    transport = FakeTransport([JsonHttpResponse(200, {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]
    }, {})])
    provider = OpenAIEmbeddingProvider(
        api_key="secret", model="text-embedding-configured", transport=transport,
    )
    assert provider.embed(["bir", "iki"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert transport.requests[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert transport.requests[0]["body"]["encoding_format"] == "float"


def test_openai_quality_judge_uses_strict_schema_and_records_evidence() -> None:
    scores = {
        name: 5 for name in (
            "language_naturalness", "tool_necessity", "tool_selection",
            "argument_grounding", "clarification_behavior", "result_grounding",
            "turkey_context",
        )
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "id": "chatcmpl-quality-1",
        "model": "gpt-quality-snapshot",
        "system_fingerprint": "fp_quality",
        "usage": {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230},
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "verdict": "pass", "scores": scores, "issues": [], "summary": "Uygun."
            })},
        }],
    }, {})])
    provider = OpenAIQualityJudge("secret", "gpt-quality", transport=transport)
    response = provider.judge_record({"id": "tctr_ot_000001"})
    request = transport.requests[0]
    assert request["url"] == "https://api.openai.com/v1/chat/completions"
    assert request["body"]["response_format"]["type"] == "json_schema"
    assert request["body"]["response_format"]["json_schema"]["strict"] is True
    assert response.value["verdict"] == "pass"
    assert response.identity.model_version == "gpt-quality-snapshot"
    assert response.usage["total_tokens"] == 230
    assert response.request_id == "chatcmpl-quality-1"
    assert response.system_fingerprint == "fp_quality"


def test_openai_quality_judge_rejects_rubric_contradiction() -> None:
    scores = {
        name: 3 for name in (
            "language_naturalness", "tool_necessity", "tool_selection",
            "argument_grounding", "clarification_behavior", "result_grounding",
            "turkey_context",
        )
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "verdict": "pass", "scores": scores, "issues": [], "summary": "Çelişkili."
            })},
        }],
    }, {})])
    with pytest.raises(ProviderError, match="valid judgment"):
        OpenAIQualityJudge("secret", "gpt-quality", transport=transport).judge_record({"id": "x"})


def test_openai_quality_judge_rejects_non_latin_script_leakage() -> None:
    scores = {
        name: 5 for name in (
            "language_naturalness", "tool_necessity", "tool_selection",
            "argument_grounding", "clarification_behavior", "result_grounding",
            "turkey_context",
        )
    }
    transport = FakeTransport([JsonHttpResponse(200, {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "verdict": "pass", "scores": scores, "issues": [], "summary": "Kullanım उचित."
            })},
        }],
    }, {})])
    with pytest.raises(ProviderError, match="valid judgment"):
        OpenAIQualityJudge("secret", "gpt-quality", transport=transport).judge_record({"id": "x"})


def test_embedding_provider_requires_explicit_model_and_key() -> None:
    with pytest.raises(ProviderNotConfigured):
        OpenAIEmbeddingProvider(api_key=None, model=None).embed(["metin"])


class CountingEmbeddingProvider:
    model = "fixture-embedding-v1"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), 1.0] for text in texts]


def test_cached_similarity_reuses_vectors_without_provider_calls(tmp_path: Path) -> None:
    provider = CountingEmbeddingProvider()
    first = CachedEmbeddingSimilarity(provider, tmp_path / "cache", batch_size=2)
    score = first.score("kısa", "daha uzun")
    assert -1.0 <= score <= 1.0
    assert provider.calls == [["kısa", "daha uzun"]]
    second = CachedEmbeddingSimilarity(provider, tmp_path / "cache", batch_size=2)
    assert second.score("kısa", "daha uzun") == score
    assert provider.calls == [["kısa", "daha uzun"]]


def test_cosine_similarity_rejects_invalid_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    with pytest.raises(ValueError, match="zero norm"):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])
