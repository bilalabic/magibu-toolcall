"""Module-based registry for `local_executable` tool functions.

Each contribution package adds one `<domain>_<source>.py` module to this package
and publishes a module-level `FUNCTIONS` mapping. No shared file is edited, so
parallel packages do not collide; `local/utility_demo.py` is the reference shape.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable

LocalFunction = Callable[[dict[str, Any]], Any]


class LocalModuleError(RuntimeError):
    """Raised when a module in this package breaks the `FUNCTIONS` contract."""


def module_names(package_name: str = __name__) -> list[str]:
    """Return the discoverable module names in deterministic (sorted) order."""

    package = importlib.import_module(package_name)
    return sorted(info.name for info in pkgutil.iter_modules(package.__path__) if not info.name.startswith("_"))


def load_functions(package_name: str = __name__) -> dict[str, LocalFunction]:
    """Merge the `FUNCTIONS` mapping of every module in `package_name`."""

    functions: dict[str, LocalFunction] = {}
    owners: dict[str, str] = {}
    for module_name in module_names(package_name):
        module = importlib.import_module(f"{package_name}.{module_name}")
        published = getattr(module, "FUNCTIONS", None)
        if not isinstance(published, dict):
            raise LocalModuleError(f"{module_name} must publish a module-level FUNCTIONS dict of local functions")
        for function_name, function in published.items():
            if function_name in functions:
                raise LocalModuleError(
                    f"duplicate local function '{function_name}': defined in both {owners[function_name]} and {module_name}"
                )
            functions[function_name] = function
            owners[function_name] = module_name
    return functions
