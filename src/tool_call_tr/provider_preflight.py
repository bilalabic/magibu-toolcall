"""Read-only provider model-access checks with secret-safe diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from tool_call_tr.config import Settings
from tool_call_tr.network import JsonTransport, NetworkError, NetworkTimeout, UrllibJsonTransport


@dataclass(frozen=True, slots=True)
class ModelAccess:
    role: str
    model: str | None
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "model": self.model, "available": self.available}


@dataclass(frozen=True, slots=True)
class ProviderAccess:
    provider: str
    status: str
    models: tuple[ModelAccess, ...]
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and all(item.available for item in self.models)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "status": self.status,
            "ok": self.ok,
            "models": [item.to_dict() for item in self.models],
        }
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        return payload


def check_provider_models(
    settings: Settings,
    *,
    providers: Iterable[str] = ("deepseek", "openai"),
    transport: JsonTransport | None = None,
) -> list[ProviderAccess]:
    """List model access without generating content or exposing response bodies."""

    selected = tuple(dict.fromkeys(providers))
    unknown = sorted(set(selected) - {"deepseek", "openai"})
    if unknown:
        raise ValueError(f"unsupported provider preflight: {', '.join(unknown)}")
    client = transport or UrllibJsonTransport()
    results: list[ProviderAccess] = []
    if "deepseek" in selected:
        results.append(
            _check_one(
                provider="deepseek",
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                expected=(
                    ("primary_generation", settings.deepseek_model),
                    ("fallback_generation", settings.deepseek_fallback_model),
                ),
                transport=client,
                timeout_seconds=settings.request_timeout_seconds,
            )
        )
    if "openai" in selected:
        results.append(
            _check_one(
                provider="openai",
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                expected=(
                    ("primary_judge", settings.openai_model),
                    ("escalation_judge", settings.openai_escalation_model),
                    ("embedding", settings.openai_embedding_model),
                ),
                transport=client,
                timeout_seconds=settings.request_timeout_seconds,
            )
        )
    return results


def _check_one(
    *,
    provider: str,
    api_key: str | None,
    base_url: str,
    expected: tuple[tuple[str, str | None], ...],
    transport: JsonTransport,
    timeout_seconds: float,
) -> ProviderAccess:
    configured_models = tuple(ModelAccess(role, model, False) for role, model in expected)
    if not api_key or any(not item.model for item in configured_models):
        return ProviderAccess(provider, "not_configured", configured_models, "PROVIDER_NOT_CONFIGURED")
    if not _safe_https_base_url(base_url):
        return ProviderAccess(provider, "blocked", configured_models, "UNSAFE_PROVIDER_BASE_URL")
    try:
        response = transport.request_json(
            method="GET",
            url=f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            body=None,
            timeout_seconds=timeout_seconds,
        )
    except (NetworkError, NetworkTimeout):
        return ProviderAccess(provider, "network_error", configured_models, "PROVIDER_NETWORK_ERROR")
    if response.status_code != 200:
        return ProviderAccess(provider, "http_error", configured_models, f"PROVIDER_HTTP_{response.status_code}")
    available = _model_ids(response.body)
    if available is None:
        return ProviderAccess(provider, "invalid_response", configured_models, "PROVIDER_INVALID_MODEL_LIST")
    models = tuple(ModelAccess(item.role, item.model, item.model in available) for item in configured_models)
    return ProviderAccess(provider, "ok", models)


def _safe_https_base_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None


def _model_ids(body: Any) -> set[str] | None:
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        return None
    identifiers: set[str] = set()
    for item in body["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            return None
        identifiers.add(item["id"])
    return identifiers
