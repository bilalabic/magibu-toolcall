"""Deterministic local implementations for the temporary small dataset pilot."""

from __future__ import annotations

import math
from typing import Any, Callable


def math_calculate_percentage(arguments: dict[str, Any]) -> dict[str, Any]:
    value = _finite_number(arguments["value"], "value")
    percentage = _finite_number(arguments["percentage"], "percentage")
    if percentage < 0 or percentage > 100:
        raise ValueError("percentage_out_of_range")
    return {
        "input_value": _normalized_number(value),
        "percentage": _normalized_number(percentage),
        "result": _normalized_number(value * percentage / 100),
    }


def unit_convert_speed(arguments: dict[str, Any]) -> dict[str, Any]:
    value = _finite_number(arguments["value"], "value")
    if value < 0:
        raise ValueError("speed_must_be_non_negative")
    input_unit = arguments["from_unit"]
    output_unit = arguments["to_unit"]
    factors_to_mps = {
        "kilometer_per_hour": 1 / 3.6,
        "meter_per_second": 1.0,
    }
    try:
        result = value * factors_to_mps[input_unit] / factors_to_mps[output_unit]
    except KeyError as exc:
        raise ValueError("unsupported_speed_unit") from exc
    return {
        "input_value": _normalized_number(value),
        "input_unit": input_unit,
        "result": _normalized_number(result),
        "output_unit": output_unit,
    }


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}_must_be_number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field}_must_be_finite")
    return normalized


def _normalized_number(value: float) -> int | float:
    rounded = round(value, 10)
    return int(rounded) if rounded.is_integer() else rounded


SMALL_PILOT_FUNCTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "math_calculate_percentage": math_calculate_percentage,
    "unit_convert_speed": unit_convert_speed,
}
