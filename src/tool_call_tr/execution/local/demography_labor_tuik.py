"""Offline executors backed by versioned TÜİK snapshots."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import unicodedata
from typing import Any

from tool_call_tr.execution.local import LocalFunction
from tool_call_tr.snapshots import snapshot_dir


SNAPSHOT_ROOT = snapshot_dir("tuik")


class TuikSnapshotError(RuntimeError):
    """The pinned local data or provenance record is missing or inconsistent."""


class TuikLookupError(ValueError):
    """A schema-valid query has no unique row in the pinned snapshot."""


def _snapshot_files(dataset: str) -> tuple[Path, Path]:
    if dataset == "migration":
        directory = SNAPSHOT_ROOT / "migration" / "v1"
        return directory / "migration_2021_2025.csv", directory / "provenance.json"
    if dataset == "unemployment":
        directory = SNAPSHOT_ROOT / "unemployment" / "v1"
        return directory / "unemployment_2021_2025.csv", directory / "provenance.json"
    raise TuikSnapshotError(f"snapshot_error: unknown dataset {dataset!r}")


def _load_snapshot(dataset: str, required_columns: set[str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    data_path, provenance_path = _snapshot_files(dataset)
    try:
        data_bytes = data_path.read_bytes()
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TuikSnapshotError(f"snapshot_error: cannot load {dataset} snapshot: {exc}") from exc

    try:
        text = data_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TuikSnapshotError(f"snapshot_error: {data_path.name} is not UTF-8") from exc

    reader = csv.DictReader(text.splitlines())
    columns = set(reader.fieldnames or ())
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        raise TuikSnapshotError(
            f"snapshot_error: {data_path.name} is missing columns: {', '.join(missing_columns)}"
        )
    rows = list(reader)
    if not rows:
        raise TuikSnapshotError(f"snapshot_error: {data_path.name} contains no records")
    return rows, provenance


def _source(provenance: dict[str, Any], *, year: int) -> dict[str, str]:
    sources = provenance.get("sources", [])
    entry = next((item for item in sources if item.get("label") == str(year)), None)
    if entry is None and len(sources) == 1:
        entry = sources[0]
    missing = [
        key
        for key in ("provider", "source_name", "snapshot_version", "retrieved_at")
        if not provenance.get(key)
    ]
    if entry is None:
        missing.append(f"sources[label={year}]")
    else:
        missing.extend(key for key in ("release_id", "source_url") if not entry.get(key))
    if missing:
        raise TuikSnapshotError(
            f"snapshot_error: provenance is missing fields: {', '.join(missing)}"
        )
    return {
        "provider": provenance["provider"],
        "dataset": entry.get("source_name", provenance["source_name"]),
        "release_id": entry["release_id"],
        "source_url": entry["source_url"],
        "snapshot_version": provenance["snapshot_version"],
        "retrieved_at": provenance["retrieved_at"],
    }


def _normalized_turkish(value: str) -> str:
    translation = str.maketrans({"ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G"})
    translated = value.strip().translate(translation).casefold()
    decomposed = unicodedata.normalize("NFKD", translated)
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(without_marks.split())


def demography_get_migration_statistics(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return one province/year/metric value from the local migration snapshot."""

    metric = arguments["metric"]
    required_columns = {
        "province",
        "year",
        "in_migration",
        "out_migration",
        "net_migration",
        "net_migration_rate",
    }
    rows, provenance = _load_snapshot("migration", required_columns)
    requested_province = _normalized_turkish(arguments["province"])
    matches = [
        row
        for row in rows
        if _normalized_turkish(row["province"]) == requested_province
        and row["year"] == str(arguments["year"])
    ]
    if not matches:
        raise TuikLookupError(
            "lookup_error: no migration row for "
            f"province={arguments['province']!r}, year={arguments['year']}"
        )
    if len(matches) != 1:
        raise TuikSnapshotError(
            "snapshot_error: migration query returned multiple rows for "
            f"province={arguments['province']!r}, year={arguments['year']}"
        )

    row = matches[0]
    try:
        if metric == "net_migration_rate":
            value: int | float = float(row[metric])
            unit = "per_thousand"
        else:
            value = int(row[metric])
            unit = "person"
    except (KeyError, ValueError) as exc:
        raise TuikSnapshotError(
            f"snapshot_error: invalid {metric} value in migration snapshot"
        ) from exc

    return {
        "province": row["province"],
        "year": int(row["year"]),
        "metric": metric,
        "value": value,
        "unit": unit,
        "source": _source(provenance, year=int(row["year"])),
    }


def labor_get_unemployment_rate(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return one annual unemployment rate from the local labor snapshot."""

    required_columns = {
        "year",
        "period",
        "country",
        "age_group",
        "unemployment_rate",
    }
    rows, provenance = _load_snapshot("unemployment", required_columns)
    matches = [
        row
        for row in rows
        if row["year"] == str(arguments["year"])
        and row["period"] == "annual"
        and row["country"] == "Türkiye"
        and row["age_group"] == "15_plus"
    ]
    if not matches:
        raise TuikLookupError(
            f"lookup_error: no unemployment row for year={arguments['year']}"
        )
    if len(matches) != 1:
        raise TuikSnapshotError(
            "snapshot_error: unemployment query returned multiple rows for "
            f"year={arguments['year']}"
        )

    row = matches[0]
    try:
        rate = float(row["unemployment_rate"])
    except ValueError as exc:
        raise TuikSnapshotError(
            "snapshot_error: invalid unemployment_rate value in unemployment snapshot"
        ) from exc
    if not 0 <= rate <= 100:
        raise TuikSnapshotError(
            "snapshot_error: unemployment_rate must be between 0 and 100"
        )

    return {
        "year": int(row["year"]),
        "period": row["period"],
        "country": row["country"],
        "age_group": row["age_group"],
        "unemployment_rate": rate,
        "unit": "percent",
        "source": _source(provenance, year=int(row["year"])),
    }


FUNCTIONS: dict[str, LocalFunction] = {
    "demography_get_migration_statistics": demography_get_migration_statistics,
    "labor_get_unemployment_rate": labor_get_unemployment_rate,
}
