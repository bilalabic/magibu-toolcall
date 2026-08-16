"""demography.get_population.v1 ve demography.compare_population.v1
için local_executable execution modülü (Paket 9 - Nüfus).

İki tool da aynı sabitlenmiş snapshot'ı okur:
data/snapshots/tuik/population/v1/population_2023_2024.csv

Deterministik ve ağsızdır; hiçbir HTTP çağrısı yapmaz.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

SNAPSHOT_ROOT = Path(__file__).resolve().parents[4] / "data" / "snapshots" / "tuik" / "population" / "v1"
DATA_FILE = SNAPSHOT_ROOT / "population_2023_2024.csv"

_CACHE: list[dict[str, Any]] | None = None


def _load_records() -> list[dict[str, Any]]:
    global _CACHE
    if _CACHE is None:
        if not DATA_FILE.exists():
            raise RuntimeError(f"snapshot_error: nüfus snapshot dosyası bulunamadı: {DATA_FILE}")
        with DATA_FILE.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            _CACHE = [
                {"province": row["province"], "year": int(row["year"]), "population": int(row["population"])}
                for row in reader
            ]
    return _CACHE


def _lookup(province: str, year: int) -> int:
    for record in _load_records():
        if record["province"] == province and record["year"] == year:
            return record["population"]
    raise RuntimeError(f"lookup_error: '{province}' ili için {year} yılına ait snapshot kaydı yok.")


def demography_get_population(arguments: dict[str, Any]) -> dict[str, Any]:
    province = arguments["province"]
    year = arguments["year"]
    population = _lookup(province, year)
    return {
        "province": province,
        "year": year,
        "population": population,
        "source": {
            "provider": "TÜİK",
            "dataset": "Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS)",
        },
    }


def demography_compare_population(arguments: dict[str, Any]) -> dict[str, Any]:
    if "province_a" in arguments and "province_b" in arguments:
        province_a = arguments["province_a"]
        province_b = arguments["province_b"]
        year = arguments["year"]
        pop_a = _lookup(province_a, year)
        pop_b = _lookup(province_b, year)
        return {
            "comparison": {
                "province_a": province_a,
                "population_a": pop_a,
                "province_b": province_b,
                "population_b": pop_b,
                "year": year,
            },
            "difference": pop_a - pop_b,
            "source": {
                "provider": "TÜİK",
                "dataset": "Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS)",
            },
        }

    if "province" in arguments and "year_a" in arguments and "year_b" in arguments:
        province = arguments["province"]
        year_a = arguments["year_a"]
        year_b = arguments["year_b"]
        pop_a = _lookup(province, year_a)
        pop_b = _lookup(province, year_b)
        return {
            "comparison": {
                "province": province,
                "population_year_a": pop_a,
                "year_a": year_a,
                "population_year_b": pop_b,
                "year_b": year_b,
            },
            "difference": pop_a - pop_b,
            "source": {
                "provider": "TÜİK",
                "dataset": "Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS)",
            },
        }

    raise RuntimeError(
        "input_error: ya (province_a, province_b, year) ya da (province, year_a, year_b) verilmelidir."
    )


FUNCTIONS = {
    "demography_get_population": demography_get_population,
    "demography_compare_population": demography_compare_population,
}