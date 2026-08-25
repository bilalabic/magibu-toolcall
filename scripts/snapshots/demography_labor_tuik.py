"""Rebuild the TÜİK migration and unemployment snapshot CSVs from their raw XLS files.

Requires `xlrd>=2.0`, which reads the legacy `.xls` format the TÜİK data portal
publishes. It is not a project dependency; install it only to run this script.

The script is offline and deterministic: it reads nothing but the files under
`data/snapshots/tuik/*/v1/raw/` and rewrites the two data files byte for byte, so
re-running it on an unchanged snapshot leaves `git diff` empty.

    python scripts/snapshots/demography_labor_tuik.py
    python scripts/snapshots/demography_labor_tuik.py --check

`--check` rebuilds in memory and compares against the committed bytes without
writing, which is what a reviewer runs to reproduce the data file.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import sys

import xlrd


SNAPSHOT_ROOT = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "tuik"
MIGRATION_DIR = SNAPSHOT_ROOT / "migration" / "v1"
UNEMPLOYMENT_DIR = SNAPSHOT_ROOT / "unemployment" / "v1"
YEARS = range(2021, 2026)
PROVINCE_COUNT = 81

# Column positions in the published migration table (sheet `t2`): the province
# name, then total population, in-migration, out-migration, net migration and the
# net migration rate. Total population is not carried into this snapshot.
MIGRATION_COLUMNS = {"province": 0, "in": 2, "out": 3, "net": 4, "rate": 5}
MIGRATION_FIRST_DATA_ROW = 4  # rows 0-2 are titles, row 3 is the `Toplam-Total` line

# The labour force table lays three blocks side by side on one sheet: total, male,
# female. This snapshot carries the total block only, so its year column and its
# unemployment rate column are the only ones read.
UNEMPLOYMENT_YEAR_COLUMN = 0
UNEMPLOYMENT_RATE_COLUMN = 8
UNEMPLOYMENT_FIRST_DATA_ROW = 5


class ConversionError(RuntimeError):
    """The raw file does not have the shape this script was written against."""


def _sheet(path: Path):
    return xlrd.open_workbook(path).sheet_by_index(0)


def _migration_rows() -> list[dict[str, object]]:
    """Return one row per province and year, year-major and province-sorted."""

    rows: list[dict[str, object]] = []
    for year in YEARS:
        sheet = _sheet(MIGRATION_DIR / "raw" / f"migration_{year}.xls")
        provinces = []
        for index in range(MIGRATION_FIRST_DATA_ROW, sheet.nrows):
            if sheet.cell_type(index, MIGRATION_COLUMNS["in"]) != xlrd.XL_CELL_NUMBER:
                continue  # the source notes printed below the table
            provinces.append(
                {
                    "province": str(sheet.cell_value(index, MIGRATION_COLUMNS["province"])).strip(),
                    "year": year,
                    "in_migration": int(sheet.cell_value(index, MIGRATION_COLUMNS["in"])),
                    "out_migration": int(sheet.cell_value(index, MIGRATION_COLUMNS["out"])),
                    "net_migration": int(sheet.cell_value(index, MIGRATION_COLUMNS["net"])),
                    "net_migration_rate": f"{sheet.cell_value(index, MIGRATION_COLUMNS['rate']):.1f}",
                }
            )
        if len(provinces) != PROVINCE_COUNT:
            raise ConversionError(
                f"migration_{year}.xls yielded {len(provinces)} provinces, expected {PROVINCE_COUNT}"
            )
        rows.extend(sorted(provinces, key=lambda row: row["province"]))
    return rows


def _unemployment_rows() -> list[dict[str, object]]:
    """Return one row per year from the total block of the labour force table."""

    sheet = _sheet(UNEMPLOYMENT_DIR / "raw" / "labor_force_indicators_15_plus_2005_2025.xls")
    rows: list[dict[str, object]] = []
    for index in range(UNEMPLOYMENT_FIRST_DATA_ROW, sheet.nrows):
        if sheet.cell_type(index, UNEMPLOYMENT_YEAR_COLUMN) != xlrd.XL_CELL_NUMBER:
            continue  # the source notes printed below the table
        year = int(sheet.cell_value(index, UNEMPLOYMENT_YEAR_COLUMN))
        if year not in YEARS:
            continue  # the published table starts at 2005; this snapshot starts at 2021
        rows.append(
            {
                "year": year,
                "period": "annual",
                "country": "Türkiye",
                "age_group": "15_plus",
                "unemployment_rate": f"{sheet.cell_value(index, UNEMPLOYMENT_RATE_COLUMN):.1f}",
            }
        )
    if len(rows) != len(YEARS):
        raise ConversionError(f"labour force table yielded {len(rows)} years, expected {len(YEARS)}")
    return rows


def _render(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the rebuilt files with the committed bytes instead of writing them",
    )
    arguments = parser.parse_args(argv)

    outputs = {
        MIGRATION_DIR / "migration_2021_2025.csv": _render(_migration_rows()),
        UNEMPLOYMENT_DIR / "unemployment_2021_2025.csv": _render(_unemployment_rows()),
    }

    drifted = []
    for path, rendered in outputs.items():
        relative = path.relative_to(SNAPSHOT_ROOT.parents[2]).as_posix()
        if arguments.check:
            if path.read_bytes() != rendered:
                drifted.append(relative)
            continue
        path.write_bytes(rendered)
        print(f"wrote {relative}")

    if drifted:
        for relative in drifted:
            print(f"DRIFT: {relative} does not match the raw files", file=sys.stderr)
        return 1
    if arguments.check:
        print(f"OK: {len(outputs)} data file(s) reproduced from raw")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
