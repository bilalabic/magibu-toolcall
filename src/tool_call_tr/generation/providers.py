"""Provider role boundaries and deterministic test doubles."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import random
import time
from typing import Any, Callable, Mapping, Protocol, TypeVar

from tool_call_tr.config import Settings
from tool_call_tr.language_plan import LanguagePlanValidationError, validate_language_plan
from tool_call_tr.network import JsonTransport, NetworkError, NetworkTimeout, UrllibJsonTransport
from tool_call_tr.text_quality import contains_unexpected_script


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        retry_after_seconds: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


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
    usage: dict[str, int] | None = None
    request_id: str | None = None
    system_fingerprint: str | None = None


class ScenarioGenerator(Protocol):
    def generate_scenario(self, blueprint: dict[str, Any]) -> ProviderResponse:
        ...


class ToolCallGenerator(Protocol):
    def generate_tool_call(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        ...


class SemanticJudge(Protocol):
    def judge(self, *, task: str, candidate: str, reference: str) -> ProviderResponse:
        ...


class RecordQualityJudge(Protocol):
    model: str

    def judge_record(self, record: dict[str, Any]) -> ProviderResponse:
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

    language_plan_max_output_tokens = 1600

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        *,
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 8192,
        transport: JsonTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_settings(cls, settings: Settings) -> "DeepSeekIntegration":
        return cls(
            settings.deepseek_api_key,
            settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.request_timeout_seconds,
            max_output_tokens=settings.deepseek_max_output_tokens,
        )

    def require_configured(self) -> None:
        if not self.api_key or not self.model:
            raise ProviderNotConfigured("DeepSeek generation/tool-call integration is not configured")

    def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        role: str,
        max_output_tokens: int | None = None,
        thinking: str | None = None,
    ) -> ProviderResponse:
        self.require_configured()
        if thinking not in {None, "enabled", "disabled"}:
            raise ValueError("DeepSeek thinking mode must be enabled or disabled")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "stream": False,
        }
        if thinking is not None:
            body["thinking"] = {"type": thinking}
        try:
            response = self.transport.request_json(
                method="POST",
                url=f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                body=body,
                timeout_seconds=self.timeout_seconds,
            )
        except NetworkTimeout as exc:
            raise ProviderError("DeepSeek request timed out") from exc
        except NetworkError as exc:
            raise ProviderError("DeepSeek network request failed") from exc
        if response.status_code == 429:
            raise ProviderError(
                "DeepSeek request was rate limited",
                retry_after_seconds=_retry_after(response.headers),
                status_code=429,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(
                f"DeepSeek request failed with HTTP {response.status_code}",
                retryable=response.status_code >= 500,
                status_code=response.status_code,
            )
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
        response_model = response.body.get("model")
        return ProviderResponse(
            value,
            ModelIdentity(
                "deepseek",
                self.model or "",
                response_model if isinstance(response_model, str) else None,
                role,
            ),
            usage=_usage(response.body.get("usage")),
            request_id=response.body.get("id") if isinstance(response.body.get("id"), str) else None,
            system_fingerprint=(
                response.body.get("system_fingerprint")
                if isinstance(response.body.get("system_fingerprint"), str)
                else None
            ),
        )

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

    def generate_language_plan(self, blueprint: dict[str, Any]) -> ProviderResponse:
        user_message_count = 2 if blueprint["metadata"]["main_category"] == "multi_turn" else 1
        intermediate_rule = (
            "a Turkish clarification question containing '?' that does not assume details only supplied by the second user message"
            if user_message_count == 2
            else "null"
        )
        chronology_rule = (
            "Chronology is user_messages[0], intermediate_assistant_response, user_messages[1], tool use, then "
            "final_response. The intermediate response sees only user_messages[0]; it must ask for the detail "
            "that user_messages[1] later supplies. "
            if user_message_count == 2
            else ""
        )
        example = (
            '{"user_messages":["Gelecek eğitim yılının tatilleri ne zaman?",'
            '"2026-2027 eğitim öğretim yılını kastediyorum."],'
            '"intermediate_assistant_response":"Hangi eğitim öğretim yılını kastediyorsunuz?",'
            '"final_response":"2026-2027 takvimini paylaşıyorum."}'
            if user_message_count == 2
            else '{"user_messages":["Ankara için hava nasıl?"],'
            '"intermediate_assistant_response":null,"final_response":"Ankara için sonuç hazır."}'
        )
        response = self.generate_json(
            system_prompt=(
                "Write only the natural-language parts of one Turkey-Turkish tool-calling dataset scenario. "
                "Return one JSON object with exactly this shape and no other keys: "
                '{"user_messages":["..."],"intermediate_assistant_response":null,"final_response":"..."}. '
                f"user_messages must contain exactly {user_message_count} non-empty string(s). "
                f"intermediate_assistant_response must be {intermediate_rule}. "
                f"{chronology_rule}"
                "final_response must follow expected_final_behavior and must_avoid, and every factual or numeric claim "
                "must be grounded in expected_tool_result or the user's messages. Translate machine enum values into "
                "natural Turkish and render ISO timestamps as natural Turkish dates and times. Include relevant result "
                "context such as event locations when the blueprint asks for it. Use natural Turkey Turkish only. "
                "Do not emit Chinese Han characters, reasoning text, <think> tags, markdown, machine metadata, tool calls, "
                f"or tool results. Example JSON output: {example}"
            ),
            payload={"blueprint": blueprint},
            role="dataset_language_generator",
            max_output_tokens=min(self.max_output_tokens, self.language_plan_max_output_tokens),
            thinking="disabled",
        )
        try:
            validate_language_plan(
                response.value,
                multi_turn=blueprint["metadata"]["main_category"] == "multi_turn",
                requires_clarification=(
                    "clarification" in blueprint["metadata"].get("secondary_tags", [])
                ),
            )
        except (KeyError, TypeError, LanguagePlanValidationError) as exc:
            reason = str(exc) if isinstance(exc, LanguagePlanValidationError) else "invalid blueprint context"
            raise ProviderError(
                f"DeepSeek language plan failed deterministic validation: {reason}"
            ) from exc
        return response

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


QUALITY_RUBRIC_VERSION = "dataset-quality-0.1.0"
QUALITY_DIMENSIONS = (
    "language_naturalness",
    "tool_necessity",
    "tool_selection",
    "argument_grounding",
    "clarification_behavior",
    "result_grounding",
    "turkey_context",
)
QUALITY_JUDGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "scores", "issues", "summary"],
    "properties": {
        "verdict": {"enum": ["pass", "uncertain", "fail"]},
        "scores": {
            "type": "object",
            "required": list(QUALITY_DIMENSIONS),
            "properties": {
                dimension: {"type": "integer", "minimum": 1, "maximum": 5}
                for dimension in QUALITY_DIMENSIONS
            },
            "additionalProperties": False,
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["code", "severity", "message", "message_index"],
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["minor", "major", "critical"]},
                    "message": {"type": "string", "minLength": 1},
                    "message_index": {"type": ["integer", "null"], "minimum": 0},
                },
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}


class OpenAIQualityJudge:
    """Independent structured-output quality judge for generated dataset records."""

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        reasoning_effort: str = "low",
        max_output_tokens: int = 1200,
        transport: JsonTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or ""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_settings(cls, settings: Settings, *, escalation: bool = False) -> "OpenAIQualityJudge":
        return cls(
            settings.openai_api_key,
            settings.openai_escalation_model if escalation else settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.request_timeout_seconds,
            reasoning_effort=settings.openai_reasoning_effort,
            max_output_tokens=settings.openai_max_output_tokens,
        )

    def require_configured(self) -> None:
        if not self.api_key or not self.model:
            raise ProviderNotConfigured("OpenAI dataset quality judge is not configured")

    def judge_record(self, record: dict[str, Any]) -> ProviderResponse:
        self.require_configured()
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an independent quality judge for a Turkish tool-calling dataset. "
                        "Evaluate natural Turkey Turkish, whether a tool is needed, selected tools, argument grounding, "
                        "clarification behavior, result grounding, and Turkey-specific realism. Machine identifiers may "
                        "remain English. Score each dimension from 1 to 5. Use pass only when every dimension is at least "
                        "4 and there are no major or critical issues. Use uncertain when evidence is insufficient. "
                        "Write summary and issue messages in natural Turkey Turkish using the Latin script only. "
                        "For missing_parameter and no_tool records, absent tool calls and results can be the correct "
                        "behavior. Evaluate whether the record correctly avoids a call and, when needed, asks for "
                        "the missing information; do not use uncertain solely because no tool result exists. "
                        f"Rubric version: {QUALITY_RUBRIC_VERSION}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"record": record}, ensure_ascii=False, sort_keys=True),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "dataset_quality_judgment",
                    "strict": True,
                    "schema": QUALITY_JUDGMENT_SCHEMA,
                },
            },
            "reasoning_effort": self.reasoning_effort,
            "max_completion_tokens": self.max_output_tokens,
            "stream": False,
        }
        try:
            response = self.transport.request_json(
                method="POST",
                url=f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                body=body,
                timeout_seconds=self.timeout_seconds,
            )
        except NetworkTimeout as exc:
            raise ProviderError("OpenAI quality request timed out") from exc
        except NetworkError as exc:
            raise ProviderError("OpenAI quality network request failed") from exc
        if response.status_code == 429:
            raise ProviderError(
                "OpenAI quality request was rate limited",
                retry_after_seconds=_retry_after(response.headers),
                status_code=429,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(
                f"OpenAI quality request failed with HTTP {response.status_code}",
                retryable=response.status_code >= 500,
                status_code=response.status_code,
            )
        try:
            choice = response.body["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ProviderError("OpenAI quality response was truncated")
            message = choice["message"]
            if message.get("refusal"):
                raise ProviderError("OpenAI quality request was refused", retryable=False)
            content = message["content"]
            value = json.loads(content)
            _validate_quality_judgment(value)
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError("OpenAI quality response was not a valid judgment") from exc
        response_model = response.body.get("model")
        return ProviderResponse(
            value,
            ModelIdentity(
                "openai",
                self.model,
                response_model if isinstance(response_model, str) else None,
                "dataset_quality_judge",
            ),
            usage=_usage(response.body.get("usage")),
            request_id=response.body.get("id") if isinstance(response.body.get("id"), str) else None,
            system_fingerprint=(
                response.body.get("system_fingerprint")
                if isinstance(response.body.get("system_fingerprint"), str)
                else None
            ),
        )


class RetryingRecordQualityJudge:
    def __init__(
        self,
        provider: RecordQualityJudge,
        policy: "RetryPolicy",
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.sleep = sleep
        self.model = provider.model

    def require_configured(self) -> None:
        method = getattr(self.provider, "require_configured", None)
        if method is not None:
            method()

    def judge_record(self, record: dict[str, Any]) -> ProviderResponse:
        response, attempts = run_with_retry(
            lambda: self.provider.judge_record(record),
            self.policy,
            retryable=lambda exc: isinstance(exc, ProviderError) and exc.retryable,
            sleep=self.sleep,
        )
        return replace(response, attempts=attempts)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 1.0
    max_seconds: float = 60.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if (
            self.max_attempts < 1
            or self.base_seconds < 0
            or self.max_seconds < self.base_seconds
            or not 0.0 <= self.jitter_ratio <= 1.0
        ):
            raise ValueError("retry policy values are invalid")


T = TypeVar("T")


def run_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None],
    random_value: Callable[[], float] = random.random,
) -> tuple[T, int]:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:
            if attempt >= policy.max_attempts or not retryable(exc):
                raise
            retry_after = getattr(exc, "retry_after_seconds", None)
            if isinstance(retry_after, (int, float)) and retry_after >= 0:
                delay = min(float(retry_after), policy.max_seconds)
            else:
                delay = min(policy.base_seconds * (2 ** (attempt - 1)), policy.max_seconds)
                jitter = (random_value() * 2.0 - 1.0) * policy.jitter_ratio
                delay = max(0.0, delay * (1.0 + jitter))
            sleep(delay)
    raise AssertionError("unreachable")


def _usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
    }
    result: dict[str, int] = {}
    for target, names in aliases.items():
        observed = next((value.get(name) for name in names if isinstance(value.get(name), int)), None)
        if observed is not None and observed >= 0:
            result[target] = observed
    if "total_tokens" not in result and {"input_tokens", "output_tokens"} <= result.keys():
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    return result or None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = next((item for key, item in headers.items() if key.casefold() == "retry-after"), None)
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _validate_quality_judgment(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"verdict", "scores", "issues", "summary"}:
        raise ValueError("invalid judgment object")
    if value["verdict"] not in {"pass", "uncertain", "fail"}:
        raise ValueError("invalid judgment verdict")
    scores = value["scores"]
    if not isinstance(scores, dict) or set(scores) != set(QUALITY_DIMENSIONS):
        raise ValueError("invalid judgment scores")
    if any(not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5 for score in scores.values()):
        raise ValueError("invalid judgment score")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("invalid judgment summary")
    if contains_unexpected_script(value["summary"]):
        raise ValueError("judgment summary contains unexpected non-Latin letters")
    issues = value["issues"]
    if not isinstance(issues, list):
        raise ValueError("invalid judgment issues")
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"code", "severity", "message", "message_index"}:
            raise ValueError("invalid judgment issue")
        if issue["severity"] not in {"minor", "major", "critical"}:
            raise ValueError("invalid judgment severity")
        if not isinstance(issue["code"], str) or not issue["code"]:
            raise ValueError("invalid judgment issue code")
        if not isinstance(issue["message"], str) or not issue["message"]:
            raise ValueError("invalid judgment issue message")
        if contains_unexpected_script(issue["message"]):
            raise ValueError("judgment issue contains unexpected non-Latin letters")
        if issue["message_index"] is not None and (
            not isinstance(issue["message_index"], int) or isinstance(issue["message_index"], bool) or issue["message_index"] < 0
        ):
            raise ValueError("invalid judgment message index")
    if value["verdict"] == "pass" and (
        min(scores.values()) < 4 or any(issue["severity"] in {"major", "critical"} for issue in issues)
    ):
        raise ValueError("pass verdict contradicts rubric evidence")
