"""Production embedding similarity with provider batching and deterministic disk cache."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Protocol, Sequence

from tool_call_tr.config import Settings
from tool_call_tr.generation.providers import ProviderError, ProviderNotConfigured
from tool_call_tr.network import JsonTransport, NetworkError, NetworkTimeout, UrllibJsonTransport


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport: JsonTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or ""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEmbeddingProvider":
        return cls(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.request_timeout_seconds,
        )

    def require_configured(self) -> None:
        if not self.api_key or not self.model:
            raise ProviderNotConfigured("OpenAI embedding integration is not configured")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.require_configured()
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("embedding input must contain non-empty strings")
        try:
            response = self.transport.request_json(
                method="POST",
                url=f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                body={"input": list(texts), "model": self.model, "encoding_format": "float"},
                timeout_seconds=self.timeout_seconds,
            )
        except NetworkTimeout as exc:
            raise ProviderError("OpenAI embeddings request timed out") from exc
        except NetworkError as exc:
            raise ProviderError("OpenAI embeddings network request failed") from exc
        if response.status_code == 429:
            raise ProviderError("OpenAI embeddings request was rate limited")
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(f"OpenAI embeddings request failed with HTTP {response.status_code}")
        try:
            values = sorted(response.body["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in values]
        except (KeyError, TypeError) as exc:
            raise ProviderError("OpenAI embeddings response has an invalid shape") from exc
        if len(vectors) != len(texts) or any(
            not isinstance(vector, list) or not vector or any(not isinstance(value, (int, float)) for value in vector)
            for vector in vectors
        ):
            raise ProviderError("OpenAI embeddings response has invalid vectors")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ProviderError("OpenAI embeddings response dimensions do not match")
        return [[float(value) for value in vector] for vector in vectors]


@dataclass(slots=True)
class CachedEmbeddingSimilarity:
    provider: EmbeddingProvider
    cache_dir: Path
    batch_size: int = 64

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ValueError("embedding batch size must be positive")

    def score(self, left: str, right: str) -> float:
        vectors = self.vectors([left, right])
        return cosine_similarity(vectors[0], vectors[1])

    def vectors(self, texts: Sequence[str]) -> list[list[float]]:
        result: list[list[float] | None] = [None] * len(texts)
        missing: dict[Path, tuple[str, list[int]]] = {}
        for index, text in enumerate(texts):
            path = self._path(text)
            if path.exists():
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    if value.get("model") == self.provider.model and isinstance(value.get("embedding"), list):
                        result[index] = [float(item) for item in value["embedding"]]
                        continue
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            if path in missing:
                missing[path][1].append(index)
            else:
                missing[path] = (text, [index])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        pending = list(missing.items())
        for start in range(0, len(pending), self.batch_size):
            batch = pending[start:start + self.batch_size]
            vectors = self.provider.embed([item[1][0] for item in batch])
            for (path, (text, indexes)), vector in zip(batch, vectors, strict=True):
                payload = {"model": self.provider.model, "text_sha256": _text_hash(text), "embedding": vector}
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
                for index in indexes:
                    result[index] = vector
        if any(item is None for item in result):
            raise ProviderError("embedding cache failed to resolve every input")
        return [item for item in result if item is not None]

    def _path(self, text: str) -> Path:
        model_hash = hashlib.sha256(self.provider.model.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / model_hash / f"{_text_hash(text)}.json"


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("embedding vectors must have equal non-zero dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding vectors cannot have zero norm")
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, score))


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
