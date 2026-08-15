from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tool_call_tr.snapshots import SCHEMA_FILENAME, main


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / SCHEMA_FILENAME


def build_snapshot(directory: Path, *, raw_bytes: bytes = b"raw;payload\n") -> dict[str, object]:
    """Write a minimal but complete single-source snapshot and return its provenance."""

    (directory / "raw").mkdir(parents=True, exist_ok=True)
    (directory / "raw" / "population_2024.xls").write_bytes(raw_bytes)
    (directory / "population_2024.csv").write_text("province,population\n", encoding="utf-8")
    return {
        "snapshot_provenance_version": "0.1.0",
        "provider": "TÜİK",
        "source_name": "Adrese Dayalı Nüfus Kayıt Sistemi, 2024",
        "snapshot_version": "tuik-population-2024-v1",
        "retrieved_at": "2026-08-15",
        "license": "TÜİK açık veri kullanım koşulları",
        "license_url": "https://data.tuik.gov.tr/license",
        "data_file": "population_2024.csv",
        "sources": [
            {
                "raw_file": "raw/population_2024.xls",
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "release_id": "49685",
                "source_url": "https://data.tuik.gov.tr/Bulten/Index?p=49685",
                "release_date": "2025-02-06",
                "label": "2024",
            }
        ],
        "transformation_notes": ["Province rows were copied verbatim from the published table."],
    }


def write_provenance(directory: Path, document: object) -> Path:
    path = directory / "provenance.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(path: Path) -> int:
    return main([str(path), "--schema", str(SCHEMA_PATH)])


def test_valid_snapshot_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_provenance(tmp_path, build_snapshot(tmp_path))

    assert run(tmp_path) == 0
    assert "OK: 1 snapshot(s) validated" in capsys.readouterr().out


def test_multi_source_snapshot_passes(tmp_path: Path) -> None:
    document = build_snapshot(tmp_path)
    second_raw = b"raw;other-year\n"
    (tmp_path / "raw" / "population_2023.xls").write_bytes(second_raw)
    document["sources"].append(
        {
            "raw_file": "raw/population_2023.xls",
            "sha256": hashlib.sha256(second_raw).hexdigest(),
            "release_id": "49684",
            "source_url": "https://data.tuik.gov.tr/Bulten/Index?p=49684",
            "release_date": "2024-02-06",
            "label": "2023",
        }
    )
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 0


def test_wrong_sha256_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = build_snapshot(tmp_path)
    document["sources"][0]["sha256"] = "0" * 64
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 1
    output = capsys.readouterr().out
    assert "ERROR SNAPSHOT_HASH_MISMATCH" in output
    assert "raw/population_2024.xls" in output


def test_missing_required_field_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = build_snapshot(tmp_path)
    del document["sources"][0]["sha256"]
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 1
    output = capsys.readouterr().out
    assert "ERROR SNAPSHOT_SCHEMA_INVALID" in output
    assert "'sha256' is a required property" in output


def test_unknown_field_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = build_snapshot(tmp_path)
    document["releases"] = {"2024": {"release_id": "49685"}}
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 1
    assert "ERROR SNAPSHOT_SCHEMA_INVALID" in capsys.readouterr().out


def test_missing_raw_file_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_provenance(tmp_path, build_snapshot(tmp_path))
    (tmp_path / "raw" / "population_2024.xls").unlink()

    assert run(tmp_path) == 1
    output = capsys.readouterr().out
    assert "ERROR SNAPSHOT_FILE_MISSING" in output
    assert "raw/population_2024.xls" in output


def test_missing_data_file_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_provenance(tmp_path, build_snapshot(tmp_path))
    (tmp_path / "population_2024.csv").unlink()

    assert run(tmp_path) == 1
    assert "ERROR SNAPSHOT_FILE_MISSING" in capsys.readouterr().out


def test_path_escaping_the_snapshot_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = build_snapshot(tmp_path)
    document["sources"][0]["raw_file"] = "raw/../../outside.xls"
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 1
    assert "ERROR SNAPSHOT_PATH_INVALID" in capsys.readouterr().out


def test_duplicate_raw_file_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = build_snapshot(tmp_path)
    duplicate = dict(document["sources"][0])
    duplicate["release_id"] = "49684"
    document["sources"].append(duplicate)
    write_provenance(tmp_path, document)

    assert run(tmp_path) == 1
    assert "raw_file declared more than once" in capsys.readouterr().out


def test_directory_walk_reports_every_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "tuik-population-2024-v1"
    bad = tmp_path / "afad-earthquake-2025-v1"
    good.mkdir()
    bad.mkdir()
    write_provenance(good, build_snapshot(good))
    broken = build_snapshot(bad)
    broken["sources"][0]["sha256"] = "1" * 64
    write_provenance(bad, broken)

    assert run(tmp_path) == 1
    assert capsys.readouterr().out.count("ERROR SNAPSHOT_HASH_MISMATCH") == 1


def test_empty_snapshot_root_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path) == 0
    assert "OK: 0 snapshot(s) validated" in capsys.readouterr().out


def test_absent_snapshot_root_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path / "snapshots") == 1
    assert "ERROR SNAPSHOT_UNREADABLE" in capsys.readouterr().out


def test_repository_snapshots_directory_validates_when_present() -> None:
    """The committed snapshot tree must stay valid, and stay optional."""

    snapshots_dir = ROOT / "data" / "snapshots"
    if not snapshots_dir.is_dir():
        pytest.skip("no committed snapshots yet")
    assert run(snapshots_dir) == 0
