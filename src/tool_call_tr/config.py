"""Environment-backed project configuration without implicit credential use."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex


ENV_PREFIX = "MAGIBU_TOOLCALL_"


def _environment_value(
    name: str,
    default: str | None = None,
    *,
    file_values: dict[str, str] | None = None,
) -> str | None:
    key = f"{ENV_PREFIX}{name}"
    return os.getenv(key, (file_values or {}).get(key, default))


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a small dotenv subset without mutating the process environment."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid .env entry on line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key.startswith(ENV_PREFIX) or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid project environment key on line {line_number}")
        raw_value = raw_value.strip()
        if raw_value.startswith(("'", '"')):
            try:
                parsed = shlex.split(raw_value, posix=True)
            except ValueError as exc:
                raise ValueError(f"invalid quoted .env value on line {line_number}") from exc
            if len(parsed) != 1:
                raise ValueError(f"invalid quoted .env value on line {line_number}")
            value = parsed[0]
        else:
            value = raw_value
        values[key] = value
    return values


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
    deepseek_max_output_tokens: int = 8192
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_escalation_model: str | None = None
    openai_embedding_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str = "low"
    openai_max_output_tokens: int = 1200
    openai_daily_token_budget: int = 2_100_000
    openai_escalation_daily_token_budget: int = 200_000
    request_timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_base_seconds: float = 1.0
    provider_max_workers: int = 1

    def __post_init__(self) -> None:
        if self.deepseek_max_output_tokens < 1 or self.openai_max_output_tokens < 1:
            raise ValueError("provider output token limits must be positive")
        if self.openai_reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
            raise ValueError("OpenAI reasoning effort is invalid")
        if self.openai_daily_token_budget < 1 or self.openai_escalation_daily_token_budget < 1:
            raise ValueError("OpenAI token budgets must be positive")
        if self.request_timeout_seconds <= 0 or self.max_retries < 0 or self.retry_base_seconds < 0:
            raise ValueError("provider retry/timeout settings are invalid")
        if not 1 <= self.provider_max_workers <= 32:
            raise ValueError("provider max workers must be between 1 and 32")

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = discover_project_root()
        file_values = _read_env_file(project_root / ".env")

        def value(name: str, default: str | None = None) -> str | None:
            return _environment_value(name, default, file_values=file_values)

        return cls(
            project_root=project_root,
            log_level=(value("LOG_LEVEL", "INFO") or "INFO").upper(),
            deepseek_api_key=value("DEEPSEEK_API_KEY") or None,
            deepseek_model=value("DEEPSEEK_MODEL") or None,
            deepseek_base_url=value("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com",
            deepseek_max_output_tokens=int(value("DEEPSEEK_MAX_OUTPUT_TOKENS", "8192") or "8192"),
            openai_api_key=value("OPENAI_API_KEY") or None,
            openai_model=value("OPENAI_MODEL") or None,
            openai_escalation_model=value("OPENAI_ESCALATION_MODEL") or None,
            openai_embedding_model=value("OPENAI_EMBEDDING_MODEL") or None,
            openai_base_url=value("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1",
            openai_reasoning_effort=value("OPENAI_REASONING_EFFORT", "low") or "low",
            openai_max_output_tokens=int(value("OPENAI_MAX_OUTPUT_TOKENS", "1200") or "1200"),
            openai_daily_token_budget=int(value("OPENAI_DAILY_TOKEN_BUDGET", "2100000") or "2100000"),
            openai_escalation_daily_token_budget=int(
                value("OPENAI_ESCALATION_DAILY_TOKEN_BUDGET", "200000") or "200000"
            ),
            request_timeout_seconds=float(value("REQUEST_TIMEOUT_SECONDS", "60") or "60"),
            max_retries=int(value("MAX_RETRIES", "2") or "2"),
            retry_base_seconds=float(
                value("RETRY_BASE_SECONDS", "1.0") or "1.0"
            ),
            provider_max_workers=int(value("PROVIDER_MAX_WORKERS", "1") or "1"),
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
