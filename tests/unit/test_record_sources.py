from __future__ import annotations

from pathlib import Path

from tool_call_tr.record_sources import record_source_sha256


def test_directory_checksum_is_deterministic_and_uses_jsonl_files(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        (directory / "b.jsonl").write_text('{"id":2}\n', encoding="utf-8")
        (directory / "a.jsonl").write_text('{"id":1}\n', encoding="utf-8")
        (directory / "notes.md").write_text("ignored", encoding="utf-8")
        fixtures = directory / "fixtures"
        fixtures.mkdir()
        (fixtures / "fixture.json").write_text("ignored", encoding="utf-8")

    assert record_source_sha256(first) == record_source_sha256(second)

    (second / "b.jsonl").write_text('{"id":3}\n', encoding="utf-8")
    assert record_source_sha256(first) != record_source_sha256(second)


def test_directory_checksum_rejects_top_level_json_records(tmp_path: Path) -> None:
    (tmp_path / "record.jsonl").write_text('{"id":1}\n', encoding="utf-8")
    (tmp_path / "record.json").write_text('{"id":2}\n', encoding="utf-8")

    try:
        record_source_sha256(tmp_path)
    except ValueError as exc:
        assert "only JSONL record files are allowed" in str(exc)
    else:
        raise AssertionError("top-level JSON record should be rejected")
