"""Deterministic conversion of the pinned TCMB bulletins into one CSV.

Reads every published bulletin under ``<snapshot>/raw`` and writes the data file
named by ``provenance.json``. Offline and byte-identical on re-run: published
rate strings are copied verbatim rather than parsed into floats, so no rounding
can enter here.

Only the standard library is required (``xml.etree``, ``csv``).

    python scripts/snapshots/finance_tcmb_historical.py

Raw acquisition is deliberately out of scope; the bulletins were downloaded once
from ``https://www.tcmb.gov.tr/kurlar/<YYYYMM>/<DDMMYYYY>.xml`` and committed as
the snapshot's evidence.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import io
from pathlib import Path
import sys
import xml.etree.ElementTree as ElementTree


DEFAULT_SNAPSHOT_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "snapshots" / "tcmb" / "exchange_rates" / "v1"
)
DATA_FILE = "exchange_rates_2026_q2.csv"
COLUMNS = ("date", "bulletin_no", "currency_code", "currency_unit", "forex_buying", "forex_selling")


class ConversionError(RuntimeError):
    """A raw bulletin does not carry the fields the snapshot depends on."""


def _text(element: ElementTree.Element, tag: str) -> str:
    return (element.findtext(tag) or "").strip()


def _bulletin_date(root: ElementTree.Element, source: Path) -> date:
    raw_date = (root.get("Tarih") or "").strip()
    try:
        return datetime.strptime(raw_date, "%d.%m.%Y").date()
    except ValueError as exc:
        raise ConversionError(f"{source.name}: unreadable Tarih attribute {raw_date!r}") from exc


def read_bulletin(path: Path) -> list[dict[str, str]]:
    """Return one row per currency that publishes both forex rates."""

    root = ElementTree.parse(path).getroot()
    published_on = _bulletin_date(root, path)
    # The published file name is DDMMYYYY; a mismatch means the wrong file was pinned.
    if path.stem != f"{published_on:%d%m%Y}":
        raise ConversionError(f"{path.name}: file name does not match bulletin date {published_on}")
    bulletin_no = (root.get("Bulten_No") or "").strip()
    if not bulletin_no:
        raise ConversionError(f"{path.name}: bulletin number is missing")

    rows: list[dict[str, str]] = []
    for currency in root.findall("Currency"):
        code = (currency.get("CurrencyCode") or "").strip()
        unit = _text(currency, "Unit")
        forex_buying = _text(currency, "ForexBuying")
        forex_selling = _text(currency, "ForexSelling")
        if not code or not unit:
            raise ConversionError(f"{path.name}: a Currency element has no code or unit")
        # XDR (SDR) publishes no selling rate; a half-filled pair stays out of the snapshot.
        if not forex_buying or not forex_selling:
            continue
        rows.append(
            {
                "date": published_on.isoformat(),
                "bulletin_no": bulletin_no,
                "currency_code": code,
                "currency_unit": unit,
                "forex_buying": forex_buying,
                "forex_selling": forex_selling,
            }
        )
    if not rows:
        raise ConversionError(f"{path.name}: no currency publishes both forex rates")
    return rows


def build_csv(raw_dir: Path) -> str:
    """Return the CSV text for every bulletin under `raw_dir`, sorted."""

    sources = sorted(raw_dir.glob("*.xml"))
    if not sources:
        raise ConversionError(f"{raw_dir}: no raw bulletin found")

    rows: list[dict[str, str]] = []
    for path in sources:
        rows.extend(read_bulletin(path))
    rows.sort(key=lambda row: (row["date"], row["currency_code"]))

    seen = {(row["date"], row["currency_code"]) for row in rows}
    if len(seen) != len(rows):
        raise ConversionError("a date/currency pair appears more than once")

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--check", action="store_true", help="verify the committed file instead of writing it")
    arguments = parser.parse_args(argv)

    snapshot_dir: Path = arguments.snapshot_dir
    target = snapshot_dir / DATA_FILE
    try:
        content = build_csv(snapshot_dir / "raw")
    except (ConversionError, ElementTree.ParseError, OSError) as exc:
        print(f"conversion failed: {exc}", file=sys.stderr)
        return 1

    if arguments.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != content:
            print(f"{target} differs from the raw bulletins", file=sys.stderr)
            return 1
        print(f"OK: {target.name} matches the raw bulletins")
        return 0

    target.write_text(content, encoding="utf-8", newline="")
    print(f"OK: wrote {target} ({content.count(chr(10)) - 1} row(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
