from __future__ import annotations

import json
import logging

import pytest

from tool_call_tr import __version__
from tool_call_tr.cli import main
from tool_call_tr.config import Settings, redact_secret
from tool_call_tr.logging import JsonFormatter


def test_package_version_is_development_version() -> None:
    assert __version__ == "0.1.0"
    assert not __version__.startswith("1.")


def test_settings_are_environment_backed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAGIBU_TOOLCALL_ROOT", str(tmp_path))
    monkeypatch.setenv("MAGIBU_TOOLCALL_MAX_RETRIES", "3")
    settings = Settings.from_env()
    assert settings.project_root == tmp_path.resolve()
    assert settings.max_retries == 3
    assert redact_secret("secret") == "<configured>"
    assert redact_secret(None) is None


def test_settings_load_ignored_project_env_without_overriding_process_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAGIBU_TOOLCALL_ROOT", str(tmp_path))
    monkeypatch.setenv("MAGIBU_TOOLCALL_OPENAI_MODEL", "process-model")
    (tmp_path / ".env").write_text(
        "MAGIBU_TOOLCALL_DEEPSEEK_API_KEY='local-secret'\n"
        "MAGIBU_TOOLCALL_OPENAI_API_KEY=local-openai-secret\n"
        "MAGIBU_TOOLCALL_OPENAI_MODEL=file-model\n",
        encoding="utf-8",
    )
    settings = Settings.from_env()
    assert settings.deepseek_api_key == "local-secret"
    assert settings.openai_api_key == "local-openai-secret"
    assert settings.openai_model == "process-model"


def test_config_never_prints_loaded_api_keys(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAGIBU_TOOLCALL_ROOT", str(tmp_path))
    (tmp_path / ".env").write_text(
        "MAGIBU_TOOLCALL_DEEPSEEK_API_KEY=deepseek-secret\n"
        "MAGIBU_TOOLCALL_OPENAI_API_KEY=openai-secret\n",
        encoding="utf-8",
    )
    assert main(["config"]) == 0
    output = capsys.readouterr().out
    assert "deepseek-secret" not in output
    assert "openai-secret" not in output
    assert output.count("<configured>") == 2
    assert "env_file=loaded" in output


def test_removed_legacy_environment_prefix_is_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MAGIBU_TOOLCALL_ROOT", raising=False)
    monkeypatch.setenv("TOOL_CALL_TR_ROOT", str(tmp_path))
    assert Settings.from_env().project_root != tmp_path.resolve()


def test_json_log_formatter() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "merhaba", (), None)
    record.event = "fixture"
    payload = json.loads(JsonFormatter().format(record))
    assert payload == {
        "event": "fixture",
        "level": "INFO",
        "logger": "test",
        "message": "merhaba",
    }


def test_cli_help_and_config(capsys, monkeypatch, tmp_path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "magibu-toolcall" in capsys.readouterr().out
    monkeypatch.setenv("MAGIBU_TOOLCALL_ROOT", str(tmp_path))
    assert main(["config"]) == 0
    assert "project_root=" in capsys.readouterr().out
