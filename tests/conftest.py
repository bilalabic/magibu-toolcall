from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_call_tr.network import UrllibJsonTransport


@pytest.fixture(autouse=True)
def block_live_provider_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches the default live HTTP transport."""

    def blocked_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("tests must inject a transport instead of using live provider network")

    monkeypatch.setattr(UrllibJsonTransport, "request_json", blocked_request)


@pytest.fixture
def access_files(tmp_path: Path) -> dict[str, str]:
    policy = {
        "policy_version": "0.1.0",
        "benchmark_dataset_team_exclusive": True,
        "principals": [
            {
                "id": "rev_language_01", "active": True, "teams": ["dataset"],
                "roles": ["language_reviewer"], "permissions": ["review", "accept"],
            },
            {
                "id": "rev_technical_01", "active": True, "teams": ["dataset"],
                "roles": ["technical_reviewer"], "permissions": ["review", "accept"],
            },
            {
                "id": "dataset_operator_01", "active": True, "teams": ["dataset", "platform"],
                "roles": ["contributor", "dataset_lead", "operator"],
                "permissions": [
                    "source_import", "localize", "generate", "quality_check", "export", "real_api",
                ],
            },
            {
                "id": "benchmark_lead_01", "active": True, "teams": ["benchmark"],
                "roles": ["technical_reviewer", "benchmark_lead"],
                "permissions": ["review", "accept", "generate", "export", "freeze", "benchmark_run"],
            },
            {
                "id": "platform_operator_01", "active": True, "teams": ["platform"],
                "roles": ["operator"], "permissions": ["real_api"],
            },
        ],
    }
    policy_path = tmp_path / "access-policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    return {"policy": str(policy_path), "audit": str(tmp_path / "audit.jsonl")}
