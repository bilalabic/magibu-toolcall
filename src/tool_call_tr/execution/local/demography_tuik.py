"""demography.get_population.v1 ve demography.compare_population.v1
için local_executable execution modülü (Paket 9 - Nüfus).

İki tool da aynı sabitlenmiş snapshot'ı okur:
data/snapshots/tuik/population/v1/population_2023_2024.csv

Deterministik ve ağsızdır; hiçbir HTTP çağrısı yapmaz.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from typing import Any

from tool_call_tr.execution.local import LocalFunction
from tool_call_tr.snapshots import snapshot_dir

SNAPSHOT_ROOT = snapshot_dir("tuik", "population", "v1")
DATA_FILE = SNAPSHOT_ROOT / "population_2023_2024.csv"
PROVENANCE_FILE = SNAPSHOT_ROOT / "provenance.json"

_PROVINCE_VS_PROVINCE = ("province_a", "province_b", "year")
_YEAR_VS_YEAR = ("province", "year_a", "year_b")


class PopulationSnapshotError(RuntimeError):
    """The pinned local data or provenance record is missing or inconsistent."""


class PopulationLookupError(ValueError):
    """A schema-valid query has no unique row in the pinned snapshot."""


def _normalized_turkish(value: str) -> str:
    """Fold Turkish letter forms and case so input matching stays tolerant."""

    translation = str.maketrans({"ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G"})
    translated = value.strip().translate(translation).casefold()
    decomposed = unicodedata.normalize("NFKD", translated)
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(without_marks.split())


def _load_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the pinned CSV and its provenance record on every call."""

    try:
        text = DATA_FILE.read_text(encoding="utf-8")
        provenance = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PopulationSnapshotError(
            f"snapshot_error: nüfus snapshot'ı okunamadı: {exc}"
        ) from exc

    reader = csv.DictReader(text.splitlines())
    missing_columns = sorted({"province", "year", "population"} - set(reader.fieldnames or ()))
    if missing_columns:
        raise PopulationSnapshotError(
            f"snapshot_error: {DATA_FILE.name} eksik sütunlar içeriyor: {', '.join(missing_columns)}"
        )

    records: list[dict[str, Any]] = []
    for row in reader:
        try:
            records.append(
                {
                    "province": row["province"],
                    "year": int(row["year"]),
                    "population": int(row["population"]),
                }
            )
        except (TypeError, ValueError) as exc:
            raise PopulationSnapshotError(
                f"snapshot_error: {DATA_FILE.name} içinde geçersiz satır: {row!r}"
            ) from exc
    if not records:
        raise PopulationSnapshotError(f"snapshot_error: {DATA_FILE.name} hiç kayıt içermiyor")
    return records, provenance


def _source(provenance: dict[str, Any]) -> dict[str, str]:
    """Build the shared six-field `source` object from the provenance record."""

    sources = provenance.get("sources") or []
    entry = sources[0] if sources else None
    missing = [
        key
        for key in ("provider", "source_name", "snapshot_version", "retrieved_at")
        if not provenance.get(key)
    ]
    if entry is None:
        missing.append("sources[0]")
    else:
        missing.extend(key for key in ("release_id", "source_url") if not entry.get(key))
    if missing:
        raise PopulationSnapshotError(
            f"snapshot_error: provenance kaydında eksik alanlar: {', '.join(missing)}"
        )
    return {
        "provider": provenance["provider"],
        "dataset": provenance["source_name"],
        "release_id": entry["release_id"],
        "source_url": entry["source_url"],
        "snapshot_version": provenance["snapshot_version"],
        "retrieved_at": provenance["retrieved_at"],
    }


def _lookup(records: list[dict[str, Any]], province: str, year: int) -> dict[str, Any]:
    """Return the snapshot row for a province/year, matching input tolerantly."""

    requested = _normalized_turkish(province)
    matches = [
        record
        for record in records
        if _normalized_turkish(record["province"]) == requested and record["year"] == year
    ]
    if not matches:
        raise PopulationLookupError(
            f"lookup_error: '{province}' ili için {year} yılına ait snapshot kaydı yok."
        )
    if len(matches) != 1:
        raise PopulationSnapshotError(
            f"snapshot_error: '{province}' ili ve {year} yılı için birden çok snapshot kaydı var."
        )
    return matches[0]


def demography_get_population(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return one province/year population from the local ADNKS snapshot."""

    records, provenance = _load_snapshot()
    record = _lookup(records, arguments["province"], arguments["year"])
    return {
        "province": record["province"],
        "year": record["year"],
        "population": record["population"],
        "source": _source(provenance),
    }


def demography_compare_population(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compare two provinces in one year, or one province across two years."""

    supplied = set(arguments)
    if supplied == set(_PROVINCE_VS_PROVINCE):
        records, provenance = _load_snapshot()
        record_a = _lookup(records, arguments["province_a"], arguments["year"])
        record_b = _lookup(records, arguments["province_b"], arguments["year"])
        return {
            "comparison": {
                "province_a": record_a["province"],
                "population_a": record_a["population"],
                "province_b": record_b["province"],
                "population_b": record_b["population"],
                "year": arguments["year"],
            },
            "difference": record_a["population"] - record_b["population"],
            "source": _source(provenance),
        }

    if supplied == set(_YEAR_VS_YEAR):
        records, provenance = _load_snapshot()
        record_a = _lookup(records, arguments["province"], arguments["year_a"])
        record_b = _lookup(records, arguments["province"], arguments["year_b"])
        return {
            "comparison": {
                "province": record_a["province"],
                "population_year_a": record_a["population"],
                "year_a": record_a["year"],
                "population_year_b": record_b["population"],
                "year_b": record_b["year"],
            },
            "difference": record_a["population"] - record_b["population"],
            "source": _source(provenance),
        }

    raise ValueError(
        "input_error: tam olarak (province_a, province_b, year) ya da "
        "(province, year_a, year_b) verilmelidir; iki mod karıştırılamaz."
    )


FUNCTIONS: dict[str, LocalFunction] = {
    "demography_get_population": demography_get_population,
    "demography_compare_population": demography_compare_population,
}
