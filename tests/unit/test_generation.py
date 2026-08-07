from __future__ import annotations

import pytest

from tool_call_tr.config import Settings
from tool_call_tr.generation import (
    DeepSeekIntegration,
    FinalResponseCoordinator,
    FinalResponseMethod,
    FinalResponseRequest,
    MockScenarioGenerator,
    MockSemanticJudge,
    MockToolCallGenerator,
    OpenAISemanticIntegration,
    ProviderNotConfigured,
    RetryPolicy,
    run_with_retry,
)


def request(**changes) -> FinalResponseRequest:
    values = {
        "user_request": "On iki ile sekizi toplar mısın?",
        "normalized_tool_result": {"result": 20},
        "execution_status": "passed",
        "tool_result_validated": True,
    }
    values.update(changes)
    return FinalResponseRequest(**values)


def test_tool_result_regeneration_is_default_and_grounded_turkish() -> None:
    outcome = FinalResponseCoordinator().generate(request())
    assert outcome.method == FinalResponseMethod.TOOL_RESULT_REGENERATION
    assert outcome.response == "Sonuç: 20."
    assert outcome.review_status == "needs_revision"


def test_source_adaptation_requires_verification() -> None:
    outcome = FinalResponseCoordinator().generate(
        request(source_answer="Sonuç: 20.", source_answer_verified=True),
        FinalResponseMethod.SOURCE_ANSWER_ADAPTATION,
    )
    assert outcome.response == "Sonuç: 20."
    unverified = FinalResponseCoordinator().generate(
        request(source_answer="Sonuç: 20.", source_answer_verified=False),
        FinalResponseMethod.SOURCE_ANSWER_ADAPTATION,
    )
    assert unverified.response is None


def test_tool_result_takes_precedence_on_source_conflict() -> None:
    outcome = FinalResponseCoordinator().generate(
        request(source_answer="Sonuç: 21.", source_answer_verified=True),
        FinalResponseMethod.SOURCE_ANSWER_ADAPTATION,
    )
    assert outcome.method == FinalResponseMethod.TOOL_RESULT_REGENERATION
    assert outcome.response == "Sonuç: 20."
    assert outcome.conflicts


def test_unverifiable_and_failure_results_are_not_hidden() -> None:
    unavailable = FinalResponseCoordinator().generate(request(normalized_tool_result=None, tool_result_validated=False))
    assert unavailable.response is None
    assert unavailable.review_status == "needs_revision"
    failed = FinalResponseCoordinator().generate(
        request(normalized_tool_result={"error": "zaman aşımı"}, execution_status="timeout")
    )
    assert "başarısız" in failed.response


def test_provider_roles_are_separate_and_mocked() -> None:
    scenario = MockScenarioGenerator({"user": "örnek"}).generate_scenario({})
    tool_call = MockToolCallGenerator({"name": "utility_add"}).generate_tool_call([], [])
    judgment = MockSemanticJudge(0.8).judge(task="direct_answer", candidate="a", reference="a")
    assert scenario.identity.role == "scenario_generator"
    assert tool_call.identity.role == "tool_call_generator"
    assert judgment.identity.role == "semantic_judge"
    assert judgment.value["passed"]


def test_provider_placeholders_require_configuration(monkeypatch) -> None:
    for name in (
        "MAGIBU_TOOLCALL_DEEPSEEK_API_KEY", "MAGIBU_TOOLCALL_DEEPSEEK_MODEL",
        "MAGIBU_TOOLCALL_OPENAI_API_KEY", "MAGIBU_TOOLCALL_OPENAI_MODEL",
        "MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    with pytest.raises(ProviderNotConfigured):
        DeepSeekIntegration.from_settings(settings).require_configured()
    with pytest.raises(ProviderNotConfigured):
        OpenAISemanticIntegration.from_settings(settings).require_configured()


def test_retry_policy_records_attempts_without_live_calls() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return "ok"

    value, used = run_with_retry(operation, RetryPolicy(3, 0.5), retryable=lambda exc: True, sleep=sleeps.append)
    assert (value, used) == ("ok", 3)
    assert sleeps == [0.5, 1.0]
