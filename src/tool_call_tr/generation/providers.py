"""Provider role boundaries and deterministic test doubles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol, TypeVar

from tool_call_tr.config import Settings
from tool_call_tr.network import JsonTransport, NetworkError, NetworkTimeout, UrllibJsonTransport


class ProviderError(RuntimeError):
    pass


class ProviderNotConfigured(ProviderError):
    pass


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    provider: str
    model: str
    model_version: str | None
    role: str


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    value: Any
    identity: ModelIdentity
    attempts: int = 1


class ScenarioGenerator(Protocol):
    def generate_scenario(self, blueprint: dict[str, Any]) -> ProviderResponse:
        ...


class ToolCallGenerator(Protocol):
    def generate_tool_call(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        ...


class SemanticJudge(Protocol):
    def judge(self, *, task: str, candidate: str, reference: str) -> ProviderResponse:
        ...


class MockScenarioGenerator:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def generate_scenario(self, blueprint: dict[str, Any]) -> ProviderResponse:
        return ProviderResponse(self.value, ModelIdentity("mock", "deterministic", "1", "scenario_generator"))


class MockToolCallGenerator:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def generate_tool_call(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        return ProviderResponse(self.value, ModelIdentity("mock", "deterministic", "1", "tool_call_generator"))


class MockSemanticJudge:
    def __init__(self, score: float = 1.0) -> None:
        self.score = score

    def judge(self, *, task: str, candidate: str, reference: str) -> ProviderResponse:
        return ProviderResponse(
            {"score": self.score, "passed": self.score >= 0.5, "task": task},
            ModelIdentity("mock", "deterministic", "1", "semantic_judge"),
        )


class DeepSeekIntegration:
    """Structured JSON generator over DeepSeek's Chat Completions endpoint."""

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        *,
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 60.0,
        transport: JsonTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_settings(cls, settings: Settings) -> "DeepSeekIntegration":
        return cls(
            settings.deepseek_api_key,
            settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.request_timeout_seconds,
        )

    def require_configured(self) -> None:
        if not self.api_key or not self.model:
            raise ProviderNotConfigured("DeepSeek generation/tool-call integration is not configured")

    def generate_json(self, *, system_prompt: str, payload: dict[str, Any], role: str) -> ProviderResponse:
        self.require_configured()
        try:
            response = self.transport.request_json(
                method="POST",
                url=f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                body={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
                    ],
                    "response_format": {"type": "json_object"},
                    "stream": False,
                },
                timeout_seconds=self.timeout_seconds,
            )
        except NetworkTimeout as exc:
            raise ProviderError("DeepSeek request timed out") from exc
        except NetworkError as exc:
            raise ProviderError("DeepSeek network request failed") from exc
        if response.status_code == 429:
            raise ProviderError("DeepSeek request was rate limited")
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(f"DeepSeek request failed with HTTP {response.status_code}")
        try:
            choice = response.body["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ProviderError("DeepSeek JSON response was truncated")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("DeepSeek returned empty JSON content")
            value = json.loads(content)
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("DeepSeek response did not contain valid structured JSON") from exc
        if not isinstance(value, dict):
            raise ProviderError("DeepSeek structured response must be a JSON object")
        return ProviderResponse(value, ModelIdentity("deepseek", self.model or "", None, role))

    def generate_scenario(self, blueprint: dict[str, Any]) -> ProviderResponse:
        return self.generate_json(
            system_prompt=(
                "Produce one Turkish tool-calling dataset candidate as a JSON object from the supplied blueprint. "
                "Preserve every machine identifier, function name, parameter key, enum value and expected argument. "
                "Set review status to needs_revision; never claim human approval."
            ),
            payload={"blueprint": blueprint},
            role="scenario_generator",
        )

    def generate_tool_call(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        return self.generate_json(
            system_prompt="Return JSON containing only the tool-call decision for the supplied messages and tools.",
            payload={"messages": messages, "tools": tools},
            role="tool_call_generator",
        )

    def generate_localization_patch(self, item: dict[str, Any], *, actor_id: str) -> ProviderResponse:
        return self.generate_json(
            system_prompt=(
                "Localize the natural-language fields into natural Turkey Turkish and return a JSON object with "
                "source_example_id, query, tool_descriptions, parameter_descriptions, response, actor_id, provider, "
                "and provider_version. Preserve all machine names and parameter keys exactly."
            ),
            payload={"source_item": item, "actor_id": actor_id, "provider": "deepseek", "provider_version": self.model},
            role="localization_generator",
        )

    def generate_candidate(self, *, lifecycle: str, blueprint: dict[str, Any], record_id: str) -> ProviderResponse:
        if lifecycle not in {"dataset", "benchmark"}:
            raise ValueError(f"unsupported generation lifecycle: {lifecycle}")
        return self.generate_json(
            system_prompt=(
                f"Produce one Turkish {lifecycle} candidate as a JSON object matching the project's canonical {lifecycle} schema. "
                f"The record ID must be {record_id}. Preserve every machine identifier, function name, parameter key, enum value "
                "and expected argument. Set review.status to needs_revision with no reviewer IDs; never claim human approval."
            ),
            payload={"lifecycle": lifecycle, "record_id": record_id, "blueprint": blueprint},
            role=f"{lifecycle}_candidate_generator",
        )


@dataclass(frozen=True, slots=True)
class OpenAISemanticIntegration:
    api_key: str | None
    model: str | None

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAISemanticIntegration":
        return cls(settings.openai_api_key, settings.openai_model)

    def require_configured(self) -> None:
        if not self.api_key or not self.model:
            raise ProviderNotConfigured("OpenAI semantic-judge integration is not configured")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.base_seconds < 0:
            raise ValueError("retry policy values are invalid")


T = TypeVar("T")


def run_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None],
) -> tuple[T, int]:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:
            if attempt >= policy.max_attempts or not retryable(exc):
                raise
            sleep(policy.base_seconds * (2 ** (attempt - 1)))
    raise AssertionError("unreachable")
