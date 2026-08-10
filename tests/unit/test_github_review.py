from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from tool_call_tr.github_review import (
    PullRequestContext,
    _safe_relative_path,
    _workflow_property_escape,
    materialize_review_tree,
    run_review,
    upsert_comment,
)


ROOT = Path(__file__).resolve().parents[2]


class FakeApi:
    def __init__(self, blobs: dict[str, bytes] | None = None, comments: list[dict] | None = None) -> None:
        self.blobs = blobs or {}
        self.comments = comments or []
        self.requests: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None):
        self.requests.append((method, path, payload))
        if "/git/blobs/" in path:
            sha = path.rsplit("/", 1)[-1]
            return {
                "encoding": "base64",
                "content": base64.b64encode(self.blobs[sha]).decode("ascii"),
            }
        return {}

    def paginated(self, path: str) -> list[dict]:
        return self.comments


def test_materialize_overlays_blobs_removes_files_and_keeps_base_schema(tmp_path: Path) -> None:
    base = tmp_path / "base"
    target = tmp_path / "target"
    (base / "blueprints").mkdir(parents=True)
    (base / "schemas").mkdir()
    (base / "registry" / "proposals" / "fixtures").mkdir(parents=True)
    (base / "blueprints" / "changed.jsonl").write_text("old\n", encoding="utf-8")
    (base / "schemas" / "common.schema.json").write_text("trusted\n", encoding="utf-8")
    (base / "registry" / "proposals" / "fixtures" / "removed.json").write_text("{}\n", encoding="utf-8")
    api = FakeApi({"blob-one": b"new\n"})

    paths = materialize_review_tree(
        base,
        target,
        repository="owner/repo",
        files=[
            {"filename": "blueprints/changed.jsonl", "status": "modified", "sha": "blob-one"},
            {"filename": "registry/proposals/fixtures/removed.json", "status": "removed", "sha": "unused"},
            {"filename": "schemas/common.schema.json", "status": "modified", "sha": "untrusted"},
        ],
        api=api,
    )

    assert paths == [
        "blueprints/changed.jsonl",
        "registry/proposals/fixtures/removed.json",
        "schemas/common.schema.json",
    ]
    assert (target / "blueprints" / "changed.jsonl").read_text(encoding="utf-8") == "new\n"
    assert not (target / "registry" / "proposals" / "fixtures" / "removed.json").exists()
    assert (target / "schemas" / "common.schema.json").read_text(encoding="utf-8") == "trusted\n"
    assert len(api.requests) == 1


@pytest.mark.parametrize("value", ["../secret", "/absolute", "folder/../../secret", "C:/absolute", ""])
def test_safe_relative_path_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="unsafe pull-request path"):
        _safe_relative_path(value)


def test_upsert_comment_updates_the_existing_bot_comment() -> None:
    api = FakeApi(
        comments=[
            {
                "id": 42,
                "body": "<!-- magibu-contribution-bot -->\nold",
                "user": {"login": "github-actions[bot]"},
            }
        ]
    )
    context = PullRequestContext("owner/repo", 7, "abc", "")

    upsert_comment(api, context, "new")

    assert api.requests == [("PATCH", "/repos/owner/repo/issues/comments/42", {"body": "new"})]


def test_workflow_property_escape_handles_command_delimiters() -> None:
    assert _workflow_property_escape("a:b,c%\n") == "a%3Ab%2Cc%25%0A"


def test_run_review_posts_a_clean_advisory_comment(tmp_path: Path) -> None:
    event = {
        "repository": {"full_name": "owner/repo"},
        "pull_request": {
            "number": 7,
            "head": {"sha": "abc"},
            "body": """
## Katkı türü
- [x] Dokümantasyon
## Değişiklik
Güncel açıklama.
## Kaynak ve lisans
Uygulanamaz.
## Otomatik kontroller
- [x] Testler geçti.
## İnsan incelemesi
- [ ] İnceleme bekleniyor.
""",
        },
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    api = FakeApi()

    report = run_review(ROOT, event_path, api)

    assert report.errors == []
    assert api.requests[-1][0:2] == ("POST", "/repos/owner/repo/issues/7/comments")
