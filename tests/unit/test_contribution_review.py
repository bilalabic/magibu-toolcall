from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from tool_call_tr.contribution_review import COMMENT_MARKER, review_contribution


ROOT = Path(__file__).resolve().parents[2]
VALID_PR_BODY = """\
## Katkı türü

- [x] Dokümantasyon

## Değişiklik

Katkı akışını açıklığa kavuşturuyor.

## Kaynak ve lisans

Uygulanamaz.

## Otomatik kontroller

- [x] Yerel testler geçti.

## İnsan incelemesi

- [ ] İnceleme bekleniyor.
"""


def _copy_review_tree(target: Path) -> None:
    for directory in ("schemas", "registry", "blueprints"):
        shutil.copytree(ROOT / directory, target / directory)


def test_current_repository_and_complete_pr_body_pass() -> None:
    report = review_contribution(
        ROOT,
        changed_paths=["README.md", "tests/unit/test_contribution_review.py"],
        pr_body=VALID_PR_BODY,
    )

    assert report.errors == []
    assert report.warnings == []
    assert "PR şablonu" in report.checks
    assert report.markdown().count(COMMENT_MARKER) == 1


def test_pr_body_requires_sections_and_a_selected_type() -> None:
    body = """\
## Katkı türü

- [ ] Tool

## Değişiklik

<!-- Açıklayın. -->
"""
    report = review_contribution(ROOT, pr_body=body)
    codes = [finding.code for finding in report.errors]

    assert "PR_CONTRIBUTION_TYPE_MISSING" in codes
    assert "PR_SECTION_EMPTY" in codes
    assert codes.count("PR_SECTION_MISSING") == 3


def test_duplicate_blueprint_id_across_files_is_reported(tmp_path: Path) -> None:
    _copy_review_tree(tmp_path)
    source = tmp_path / "blueprints" / "pilot_general.jsonl"
    duplicate = tmp_path / "blueprints" / "duplicate.jsonl"
    duplicate.write_text(source.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    report = review_contribution(tmp_path, changed_paths=["blueprints/duplicate.jsonl"])

    finding = next(item for item in report.errors if item.code == "BLUEPRINT_ID_DUPLICATE_ACROSS_FILES")
    assert finding.file == "blueprints/pilot_general.jsonl" or finding.file == "blueprints/duplicate.jsonl"
    assert finding.line == 1


def test_execution_change_without_test_produces_advisory_warning() -> None:
    report = review_contribution(
        ROOT,
        changed_paths=["src/tool_call_tr/execution/adapters.py"],
    )

    assert report.errors == []
    assert {finding.code for finding in report.warnings} == {"EXECUTION_TEST_MISSING"}


def test_changed_text_file_with_secret_pattern_is_rejected(tmp_path: Path) -> None:
    _copy_review_tree(tmp_path)
    secret_file = tmp_path / "blueprints" / "accidental-secret.txt"
    fake_secret = "s" + "k-this_is_a_fake_test_token_123456789"
    secret_file.write_text(f"token={fake_secret}\n", encoding="utf-8")

    report = review_contribution(tmp_path, changed_paths=["blueprints/accidental-secret.txt"])

    finding = next(item for item in report.errors if item.code == "SECRET_OPENAI_STYLE")
    assert finding.file == "blueprints/accidental-secret.txt"
    assert finding.line == 1


@pytest.mark.parametrize("path", ["../outside.json", "C:/outside.json", ""])
def test_unsafe_changed_path_is_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="unsafe contribution path"):
        review_contribution(ROOT, changed_paths=[path])


def test_invalid_undeclared_fixture_is_reported(tmp_path: Path) -> None:
    _copy_review_tree(tmp_path)
    fixture = tmp_path / "registry" / "proposals" / "fixtures" / "broken.json"
    fixture.write_text("{not-json}\n", encoding="utf-8")

    report = review_contribution(tmp_path, changed_paths=["registry/proposals/fixtures/broken.json"])

    assert "FIXTURE_FILE_INVALID" in {finding.code for finding in report.errors}


def test_missing_schema_directory_is_reported_without_crashing(tmp_path: Path) -> None:
    report = review_contribution(tmp_path)

    assert [finding.code for finding in report.errors] == ["SCHEMA_STORE_INVALID"]
