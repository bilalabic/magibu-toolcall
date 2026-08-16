"""Offline executors backed by the versioned TCMB exchange-rate snapshot.

Both functions answer from the pinned 2026 Q2 bulletins. Published rate strings
are read as `Decimal`, so an answer carries the bulletin's own precision and any
derived number is rounded once, deliberately.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

from tool_call_tr.execution.local import LocalFunction
from tool_call_tr.snapshots import snapshot_dir


SNAPSHOT_ROOT = snapshot_dir("tcmb", "exchange_rates", "v1")
DATA_FILE = "exchange_rates_2026_q2.csv"
COLUMNS = {"date", "bulletin_no", "currency_code", "currency_unit", "forex_buying", "forex_selling"}
RATE_COLUMNS = {"forex_buying": "forex_buying", "forex_selling": "forex_selling"}
CHANGE_DIGITS = Decimal("0.0001")
PERCENT_DIGITS = Decimal("0.01")


class TcmbSnapshotError(RuntimeError):
    """The pinned bulletins or their provenance record are missing or inconsistent."""


class TcmbCoverageError(ValueError):
    """A schema-valid date falls outside the window the snapshot pins."""


class TcmbLookupError(ValueError):
    """A requested bulletin day exists in the window but was never published."""


def _load_snapshot() -> tuple[list[dict[str, str]], dict[str, Any]]:
    data_path = SNAPSHOT_ROOT / DATA_FILE
    provenance_path = SNAPSHOT_ROOT / "provenance.json"
    try:
        text = data_path.read_text(encoding="utf-8")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TcmbSnapshotError(f"snapshot_error: cannot load TCMB snapshot: {exc}") from exc

    reader = csv.DictReader(text.splitlines())
    missing_columns = sorted(COLUMNS - set(reader.fieldnames or ()))
    if missing_columns:
        raise TcmbSnapshotError(
            f"snapshot_error: {DATA_FILE} is missing columns: {', '.join(missing_columns)}"
        )
    rows = list(reader)
    if not rows:
        raise TcmbSnapshotError(f"snapshot_error: {DATA_FILE} contains no records")
    return rows, provenance


def _source(provenance: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, str]:
    """Describe the snapshot as a whole; each observation carries its own bulletin."""

    missing = [
        key
        for key in ("provider", "source_name", "snapshot_version", "retrieved_at", "sources")
        if not provenance.get(key)
    ]
    if missing:
        raise TcmbSnapshotError(f"snapshot_error: provenance is missing fields: {', '.join(missing)}")
    # Bulletin numbers are strings, so the range is taken in date order:
    # sorting "2026/99" and "2026/100" as text reverses them.
    by_date = sorted({(row["date"], row["bulletin_no"]) for row in rows})
    return {
        "provider": provenance["provider"],
        "dataset": provenance["source_name"],
        "release_id": f"{by_date[0][1]}-{by_date[-1][1]}",
        "source_url": "https://www.tcmb.gov.tr/kurlar/kurlar_tr.html",
        "snapshot_version": provenance["snapshot_version"],
        "retrieved_at": provenance["retrieved_at"],
    }


def _coverage(rows: list[dict[str, str]]) -> tuple[date, date]:
    days = {row["date"] for row in rows}
    try:
        return date.fromisoformat(min(days)), date.fromisoformat(max(days))
    except ValueError as exc:
        raise TcmbSnapshotError("snapshot_error: snapshot holds an unreadable date") from exc


def _parsed_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TcmbCoverageError(f"coverage_error: {field} is not an ISO 8601 date: {value!r}") from exc


def _require_covered(day: date, field: str, first: date, last: date) -> None:
    if not first <= day <= last:
        raise TcmbCoverageError(
            f"coverage_error: {field}={day.isoformat()} is outside the pinned window "
            f"{first.isoformat()}..{last.isoformat()}"
        )


def _decimal(row: dict[str, str], column: str) -> Decimal:
    try:
        return Decimal(row[column])
    except (KeyError, InvalidOperation) as exc:
        raise TcmbSnapshotError(
            f"snapshot_error: invalid {column} value on {row.get('date')} for {row.get('currency_code')}"
        ) from exc


def _currency_unit(row: dict[str, str]) -> int:
    try:
        unit = int(row["currency_unit"])
    except (KeyError, ValueError) as exc:
        raise TcmbSnapshotError(
            f"snapshot_error: invalid currency_unit on {row.get('date')} for {row.get('currency_code')}"
        ) from exc
    if unit < 1:
        raise TcmbSnapshotError(f"snapshot_error: currency_unit must be positive on {row['date']}")
    return unit


def _observation(row: dict[str, str], column: str) -> dict[str, Any]:
    return {
        "date": row["date"],
        "rate": float(_decimal(row, column)),
        "bulletin_no": row["bulletin_no"],
    }


def finance_search_historical_rates(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return every pinned bulletin rate for one currency inside a date range."""

    rows, provenance = _load_snapshot()
    first, last = _coverage(rows)
    start = _parsed_date(arguments["start_date"], "start_date")
    end = _parsed_date(arguments["end_date"], "end_date")
    if start > end:
        raise TcmbCoverageError(
            f"coverage_error: start_date={start.isoformat()} is later than end_date={end.isoformat()}"
        )
    _require_covered(start, "start_date", first, last)
    _require_covered(end, "end_date", first, last)

    currency_code = arguments["currency_code"]
    column = RATE_COLUMNS[arguments["rate_type"]]
    matched = [
        row
        for row in rows
        if row["currency_code"] == currency_code
        and start <= date.fromisoformat(row["date"]) <= end
    ]
    matched.sort(key=lambda row: row["date"])

    observations = [_observation(row, column) for row in matched]
    # A range that holds no bulletin day is an empty answer, not a failure. The
    # list is date-ordered, so max/min resolve a tie to the earliest bulletin.
    highest = max(observations, key=lambda item: item["rate"], default=None)
    lowest = min(observations, key=lambda item: item["rate"], default=None)
    return {
        "currency_code": currency_code,
        "currency_unit": _currency_unit(matched[0]) if matched else _snapshot_unit(rows, currency_code),
        "rate_type": arguments["rate_type"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "count": len(observations),
        "rates": observations,
        "highest": highest,
        "lowest": lowest,
        "unit": "try_per_currency_unit",
        "source": _source(provenance, rows),
    }


def _snapshot_unit(rows: list[dict[str, str]], currency_code: str) -> int:
    """Return a currency's published unit even when the queried range is empty."""

    for row in rows:
        if row["currency_code"] == currency_code:
            return _currency_unit(row)
    raise TcmbSnapshotError(f"snapshot_error: {currency_code} is not present in the snapshot")


def finance_compare_historical_rates(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compare pinned bulletin rates across the requested dates, per currency."""

    rows, provenance = _load_snapshot()
    first, last = _coverage(rows)
    column = RATE_COLUMNS[arguments["rate_type"]]
    days = [_parsed_date(value, "dates") for value in arguments["dates"]]
    for day in days:
        _require_covered(day, "dates", first, last)
    days.sort()

    published = {row["date"] for row in rows}
    unpublished = [day.isoformat() for day in days if day.isoformat() not in published]
    if unpublished:
        raise TcmbLookupError(
            "lookup_error: TCMB published no bulletin on " + ", ".join(unpublished)
        )

    by_key = {(row["date"], row["currency_code"]): row for row in rows}
    comparisons: list[dict[str, Any]] = []
    for currency_code in sorted(arguments["currency_codes"]):
        matched = [by_key[(day.isoformat(), currency_code)] for day in days]
        observations = [_observation(row, column) for row in matched]
        change: float | None = None
        change_percent: float | None = None
        if len(observations) >= 2:
            # Same currency, so the published unit is constant and the difference is sound.
            opening = _decimal(matched[0], column)
            closing = _decimal(matched[-1], column)
            change = float((closing - opening).quantize(CHANGE_DIGITS))
            change_percent = float(((closing - opening) / opening * 100).quantize(PERCENT_DIGITS))
        comparisons.append(
            {
                "currency_code": currency_code,
                "currency_unit": _currency_unit(matched[0]),
                "observations": observations,
                "change": change,
                "change_percent": change_percent,
            }
        )

    return {
        "rate_type": arguments["rate_type"],
        "dates": [day.isoformat() for day in days],
        "count": len(comparisons),
        "comparisons": comparisons,
        "unit": "try_per_currency_unit",
        "source": _source(provenance, rows),
    }


FUNCTIONS: dict[str, LocalFunction] = {
    "finance_search_historical_rates": finance_search_historical_rates,
    "finance_compare_historical_rates": finance_compare_historical_rates,
}
