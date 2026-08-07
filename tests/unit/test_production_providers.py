from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tool_call_tr.generation.providers import DeepSeekIntegration, ProviderError, ProviderNotConfigured
from tool_call_tr.network import JsonHttpResponse
from tool_call_tr.semantic import CachedEmbeddingSimilarity, OpenAIEmbeddingProvider, cosine_similarity


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
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"ok": True})}}]
    }, {})])
    provider = DeepSeekIntegration("secret", "configured-model", transport=transport)
    response = provider.generate_json(system_prompt="Return JSON.", payload={"input": 1}, role="scenario_generator")
    assert response.value == {"ok": True}
    assert response.identity.provider == "deepseek"
    assert transport.requests[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert transport.requests[0]["body"]["response_format"] == {"type": "json_object"}


def test_deepseek_errors_never_echo_secret_or_response_body() -> None:
    transport = FakeTransport([JsonHttpResponse(500, {"error": "contains-sensitive-upstream-text"}, {})])
    provider = DeepSeekIntegration("top-secret", "configured-model", transport=transport)
    with pytest.raises(ProviderError) as raised:
        provider.generate_json(system_prompt="Return JSON.", payload={}, role="scenario_generator")
    assert "top-secret" not in str(raised.value)
    assert "contains-sensitive" not in str(raised.value)


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
