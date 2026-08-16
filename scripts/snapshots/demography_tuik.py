"""TÜİK ADNKS il nüfusu ham verisini (raw/) sürümlü snapshot dosyasına dönüştürür.

Girdi : data/snapshots/tuik/population/v1/raw/adnks_il_nufus_2023_2024.csv
Cıktı : data/snapshots/tuik/population/v1/population_2023_2024.csv

Çalıştırma:
    python scripts\\snapshots\\demography_tuik.py

Bağımlılık: yalnız standart kütüphane. Deterministiktir: aynı girdi
her zaman aynı çıktıyı üretir (satır sıralaması sabittir).
"""

from __future__ import annotations

import csv
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "tuik" / "population" / "v1"
RAW_FILE = SNAPSHOT_DIR / "raw" / "adnks_il_nufus_2023_2024.csv"
OUTPUT_FILE = SNAPSHOT_DIR / "population_2023_2024.csv"


def main() -> None:
    with RAW_FILE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [
            {"province": row["province"], "year": int(row["year"]), "population": int(row["population"])}
            for row in reader
        ]

    # Deterministik sıralama: il adı, sonra yıl.
    rows.sort(key=lambda r: (r["province"], r["year"]))

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["province", "year", "population"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Yazıldı: {OUTPUT_FILE} ({len(rows)} satır)")


if __name__ == "__main__":
    main()