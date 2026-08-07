"""Environment-backed project configuration without implicit credential use."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ENV_PREFIX = "MAGIBU_TOOLCALL_"


def _environment_value(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"{ENV_PREFIX}{name}", default)


def discover_project_root() -> Path:
    configured = _environment_value("ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    log_level: str = "INFO"
    deepseek_api_key: str | None = None
    deepseek_model: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_embedding_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    request_timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_base_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_root=discover_project_root(),
            log_level=(_environment_value("LOG_LEVEL", "INFO") or "INFO").upper(),
            deepseek_api_key=_environment_value("DEEPSEEK_API_KEY") or None,
            deepseek_model=_environment_value("DEEPSEEK_MODEL") or None,
            deepseek_base_url=_environment_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com",
            openai_api_key=_environment_value("OPENAI_API_KEY") or None,
            openai_model=_environment_value("OPENAI_MODEL") or None,
            openai_embedding_model=_environment_value("OPENAI_EMBEDDING_MODEL") or None,
            openai_base_url=_environment_value("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1",
            request_timeout_seconds=float(_environment_value("REQUEST_TIMEOUT_SECONDS", "60") or "60"),
            max_retries=int(_environment_value("MAX_RETRIES", "2") or "2"),
            retry_base_seconds=float(
                _environment_value("RETRY_BASE_SECONDS", "1.0") or "1.0"
            ),
        )

    @property
    def schemas_dir(self) -> Path:
        return self.project_root / "schemas"

    @property
    def registry_path(self) -> Path:
        return self.project_root / "registry" / "registry.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.project_root / "runs"

    @property
    def semantic_cache_dir(self) -> Path:
        configured = _environment_value("SEMANTIC_CACHE_DIR")
        return Path(configured).expanduser().resolve() if configured else self.project_root / ".cache" / "semantic"


def redact_secret(value: str | None) -> str | None:
    """Return a safe marker for config diagnostics, never the secret itself."""

    return "<configured>" if value else None
