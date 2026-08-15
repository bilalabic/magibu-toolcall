"""Reference `local_executable` module: deterministic arithmetic utilities."""

from __future__ import annotations

from typing import Any

from tool_call_tr.execution.local import LocalFunction


def utility_add(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the sum of the two given numbers."""

    return {"result": arguments["left"] + arguments["right"]}


def utility_multiply(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the product of the two given numbers."""

    return {"result": arguments["left"] * arguments["right"]}


FUNCTIONS: dict[str, LocalFunction] = {
    "utility_add": utility_add,
    "utility_multiply": utility_multiply,
}
