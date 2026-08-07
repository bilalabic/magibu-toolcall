"""Safe deterministic implementations for locally executable pilot tools."""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
import math
import operator
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_MAX_RESULT_MAGNITUDE = 1e18
_MAX_AST_NODES = 50
_MAX_EXPONENT_MAGNITUDE = 12


def calculator_evaluate(arguments: dict[str, Any]) -> dict[str, Any]:
    expression = arguments["expression"].strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ValueError("invalid_arithmetic_expression") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ValueError("arithmetic_expression_too_complex")
    result = _evaluate_node(tree.body)
    if not math.isfinite(result) or abs(result) > _MAX_RESULT_MAGNITUDE:
        raise ValueError("arithmetic_result_out_of_range")
    return {"result": result, "normalized_expression": ast.unparse(tree.body)}


def _evaluate_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT_MAGNITUDE:
            raise ValueError("arithmetic_exponent_out_of_range")
        try:
            result = _BINARY_OPERATORS[type(node.op)](left, right)
        except (ArithmeticError, OverflowError) as exc:
            raise ValueError("arithmetic_operation_failed") from exc
        if not math.isfinite(result) or abs(result) > _MAX_RESULT_MAGNITUDE:
            raise ValueError("arithmetic_result_out_of_range")
        return result
    raise ValueError("arithmetic_operation_not_allowed")


# Each unit maps to (dimension, scale, offset). Base value = value * scale + offset.
_UNITS: dict[str, tuple[str, float, float]] = {
    "millimeter": ("length", 0.001, 0.0),
    "centimeter": ("length", 0.01, 0.0),
    "meter": ("length", 1.0, 0.0),
    "kilometer": ("length", 1000.0, 0.0),
    "inch": ("length", 0.0254, 0.0),
    "foot": ("length", 0.3048, 0.0),
    "yard": ("length", 0.9144, 0.0),
    "mile": ("length", 1609.344, 0.0),
    "gram": ("mass", 0.001, 0.0),
    "kilogram": ("mass", 1.0, 0.0),
    "pound": ("mass", 0.45359237, 0.0),
    "meter_per_second": ("speed", 1.0, 0.0),
    "kilometer_per_hour": ("speed", 1 / 3.6, 0.0),
    "mile_per_hour": ("speed", 0.44704, 0.0),
    "kelvin": ("temperature", 1.0, 0.0),
    "celsius": ("temperature", 1.0, 273.15),
    "fahrenheit": ("temperature", 5 / 9, 255.3722222222222),
}


def calculator_convert_units(arguments: dict[str, Any]) -> dict[str, Any]:
    from_unit = arguments["from_unit"]
    to_unit = arguments["to_unit"]
    try:
        from_dimension, from_scale, from_offset = _UNITS[from_unit]
        to_dimension, to_scale, to_offset = _UNITS[to_unit]
    except KeyError as exc:
        raise ValueError(f"unsupported_unit:{exc.args[0]}") from exc
    if from_dimension != to_dimension:
        raise ValueError("incompatible_unit_dimensions")
    value = float(arguments["value"])
    base_value = value * from_scale + from_offset
    converted = (base_value - to_offset) / to_scale
    if not math.isfinite(converted):
        raise ValueError("unit_conversion_result_out_of_range")
    result = 0.0 if converted == 0 else round(converted, 12)
    return {
        "input_value": arguments["value"],
        "input_unit": from_unit,
        "result": result,
        "output_unit": to_unit,
    }


def time_convert_timezone(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        local_datetime = datetime.fromisoformat(arguments["local_datetime"])
    except ValueError as exc:
        raise ValueError("invalid_local_datetime") from exc
    if local_datetime.tzinfo is not None:
        raise ValueError("local_datetime_must_not_include_utc_offset")
    try:
        source_zone = ZoneInfo(arguments["source_timezone"])
        target_zone = ZoneInfo(arguments["target_timezone"])
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown_iana_timezone") from exc

    fold_zero = local_datetime.replace(tzinfo=source_zone, fold=0)
    fold_one = local_datetime.replace(tzinfo=source_zone, fold=1)
    zero_valid = _round_trips(fold_zero, local_datetime, source_zone)
    one_valid = _round_trips(fold_one, local_datetime, source_zone)
    if not zero_valid and not one_valid:
        raise ValueError("nonexistent_local_datetime")
    ambiguous = zero_valid and one_valid and fold_zero.utcoffset() != fold_one.utcoffset()
    source_datetime = fold_zero if zero_valid else fold_one
    target_datetime = source_datetime.astimezone(target_zone)
    return {
        "source_datetime": source_datetime.isoformat(),
        "target_datetime": target_datetime.isoformat(),
        "source_utc_offset": _format_offset(source_datetime),
        "target_utc_offset": _format_offset(target_datetime),
        "ambiguous": ambiguous,
    }


def _round_trips(value: datetime, expected_local: datetime, zone: ZoneInfo) -> bool:
    return value.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == expected_local


def _format_offset(value: datetime) -> str:
    rendered = value.strftime("%z")
    return f"{rendered[:3]}:{rendered[3:]}"


_FULL_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "Yılbaşı",
    date(2026, 3, 20): "Ramazan Bayramı 1. Gün",
    date(2026, 3, 21): "Ramazan Bayramı 2. Gün",
    date(2026, 3, 22): "Ramazan Bayramı 3. Gün",
    date(2026, 4, 23): "Ulusal Egemenlik ve Çocuk Bayramı",
    date(2026, 5, 1): "Emek ve Dayanışma Günü",
    date(2026, 5, 19): "Atatürk'ü Anma, Gençlik ve Spor Bayramı",
    date(2026, 5, 27): "Kurban Bayramı 1. Gün",
    date(2026, 5, 28): "Kurban Bayramı 2. Gün",
    date(2026, 5, 29): "Kurban Bayramı 3. Gün",
    date(2026, 5, 30): "Kurban Bayramı 4. Gün",
    date(2026, 7, 15): "Demokrasi ve Millî Birlik Günü",
    date(2026, 8, 30): "Zafer Bayramı",
    date(2026, 10, 29): "Cumhuriyet Bayramı",
}
_HALF_DAY_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 3, 19): "Ramazan Bayramı Arifesi",
    date(2026, 5, 26): "Kurban Bayramı Arifesi",
    date(2026, 10, 28): "Cumhuriyet Bayramı Arifesi",
}


def holiday_is_business_day(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        requested_date = date.fromisoformat(arguments["date"])
    except ValueError as exc:
        raise ValueError("invalid_date") from exc
    if requested_date.year != 2026:
        raise ValueError("unsupported_holiday_year")
    if requested_date in _FULL_HOLIDAYS_2026:
        status = "public_holiday"
        holiday_name: str | None = _FULL_HOLIDAYS_2026[requested_date]
    elif requested_date in _HALF_DAY_HOLIDAYS_2026:
        status = "half_day_holiday"
        holiday_name = _HALF_DAY_HOLIDAYS_2026[requested_date]
    elif requested_date.weekday() >= 5:
        status = "weekend"
        holiday_name = None
    else:
        status = "business_day"
        holiday_name = None
    return {
        "date": requested_date.isoformat(),
        "day_status": status,
        "is_full_business_day": status == "business_day",
        "holiday_name": holiday_name,
        "source_version": "tr-holidays-2026-v1",
    }


LOCAL_PILOT_FUNCTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "calculator_evaluate": calculator_evaluate,
    "calculator_convert_units": calculator_convert_units,
    "time_convert_timezone": time_convert_timezone,
    "holiday_is_business_day": holiday_is_business_day,
}
