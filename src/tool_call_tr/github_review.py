"""Safe GitHub pull-request materialization and advisory review."""

from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tool_call_tr.contribution_review import COMMENT_MARKER, ContributionReport, review_contribution


GITHUB_API = "https://api.github.com"
_BASE_DIRECTORIES = (
    "schemas",
    "registry",
    "blueprints",
    "data/dataset/accepted",
    "data/dataset/needs_revision",
    "review/dataset",
)


class GitHubApiError(RuntimeError):
    """Raised when GitHub does not return the expected API response."""


@dataclass(frozen=True, slots=True)
class PullRequestContext:
    repository: str
    number: int
    head_sha: str
    body: str


class GitHubApi:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "magibu-toolcall-contribution-review",
        }

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(f"{GITHUB_API}{path}", data=data, headers=self._headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubApiError(f"GitHub API {method} {path} failed ({exc.code}): {detail}") from exc

    def paginated(self, path: str) -> list[dict[str, Any]]:
        separator = "&" if "?" in path else "?"
        results: list[dict[str, Any]] = []
        for page in range(1, 101):
            batch = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise GitHubApiError(f"GitHub API returned a non-list response for {path}")
            results.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                return results
        raise GitHubApiError(f"GitHub API pagination limit exceeded for {path}")


def load_context(event_path: Path) -> PullRequestContext:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = event["pull_request"]
    return PullRequestContext(
        repository=event["repository"]["full_name"],
        number=int(pull_request["number"]),
        head_sha=pull_request["head"]["sha"],
        body=pull_request.get("body") or "",
    )


def changed_files(api: GitHubApi, context: PullRequestContext) -> list[dict[str, Any]]:
    return api.paginated(f"/repos/{context.repository}/pulls/{context.number}/files")


def materialize_review_tree(
    base_root: Path,
    target_root: Path,
    *,
    repository: str,
    files: Iterable[dict[str, Any]],
    api: GitHubApi,
) -> list[str]:
    """Overlay PR blobs on trusted contracts without checking out or executing PR code."""

    for relative in _BASE_DIRECTORIES:
        source = base_root / relative
        if source.exists():
            shutil.copytree(source, target_root / relative, dirs_exist_ok=True)

    paths: list[str] = []
    for item in files:
        relative = _safe_relative_path(str(item["filename"]))
        paths.append(relative)
        previous = item.get("previous_filename")
        if isinstance(previous, str):
            _remove_path(target_root, _safe_relative_path(previous))
        if item.get("status") == "removed":
            _remove_path(target_root, relative)
            continue

        # Schemas are executable validation policy. pull_request_target must use
        # the trusted base version; schema changes are flagged for normal CI and review.
        if relative.startswith("schemas/"):
            continue
        sha = item.get("sha")
        if not isinstance(sha, str) or not sha:
            raise GitHubApiError(f"missing blob SHA for {relative}")
        blob = api.request("GET", f"/repos/{repository}/git/blobs/{quote(sha, safe='')}")
        if not isinstance(blob, dict) or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise GitHubApiError(f"unsupported blob response for {relative}")
        try:
            encoded = "".join(blob["content"].split())
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GitHubApiError(f"invalid base64 blob for {relative}") from exc
        destination = target_root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return sorted(set(paths))


def upsert_comment(api: GitHubApi, context: PullRequestContext, body: str) -> None:
    comments = api.paginated(f"/repos/{context.repository}/issues/{context.number}/comments")
    for comment in comments:
        author = comment.get("user") if isinstance(comment.get("user"), dict) else {}
        if COMMENT_MARKER in str(comment.get("body", "")) and author.get("login") == "github-actions[bot]":
            api.request("PATCH", f"/repos/{context.repository}/issues/comments/{comment['id']}", {"body": body})
            return
    api.request("POST", f"/repos/{context.repository}/issues/{context.number}/comments", {"body": body})


def emit_annotations(report: ContributionReport) -> None:
    for finding in report.findings:
        level = "error" if finding.severity == "error" else "warning"
        properties: list[str] = []
        if finding.file:
            properties.append(f"file={_workflow_property_escape(finding.file)}")
        if finding.line:
            properties.append(f"line={finding.line}")
        suffix = " " + ",".join(properties) if properties else ""
        message = _workflow_escape(f"{finding.code}: {finding.message} Düzeltme: {finding.suggestion}")
        print(f"::{level}{suffix}::{message}")


def write_summary(markdown: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(markdown)


def run_review(base_root: Path, event_path: Path, api: GitHubApi) -> ContributionReport:
    context = load_context(event_path)
    files = changed_files(api, context)
    with tempfile.TemporaryDirectory(prefix="magibu-pr-review-") as directory:
        review_root = Path(directory)
        paths = materialize_review_tree(
            base_root,
            review_root,
            repository=context.repository,
            files=files,
            api=api,
        )
        report = review_contribution(review_root, changed_paths=paths, pr_body=context.body)
    markdown = report.markdown()
    emit_annotations(report)
    write_summary(markdown)
    upsert_comment(api, context, markdown)
    return report


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Review a GitHub pull request without executing PR code.")
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--blocking", action="store_true", help="Return non-zero when deterministic errors exist.")
    args = parser.parse_args(argv)
    api = GitHubApi(os.environ.get("GITHUB_TOKEN", ""))
    report = run_review(args.repository_root.resolve(), args.event_path.resolve(), api)
    return int(args.blocking and report.has_errors)


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
        raise ValueError(f"unsafe pull-request path: {value}")
    return path.as_posix()


def _remove_path(root: Path, relative: str) -> None:
    path = root / Path(relative)
    if path.is_file() or path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _workflow_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _workflow_property_escape(value: str) -> str:
    return _workflow_escape(value).replace(":", "%3A").replace(",", "%2C")


if __name__ == "__main__":
    raise SystemExit(main())
