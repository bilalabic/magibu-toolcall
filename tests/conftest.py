from __future__ import annotations

import json
from pathlib import Path

import pytest


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
                "id": "dataset_operator_01", "active": True, "teams": ["dataset"],
                "roles": ["contributor", "dataset_lead"],
                "permissions": ["source_import", "localize", "generate", "export"],
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
