"""Module-based registry for `fully_simulated` tools.

Each contribution package adds one `<domain>_<source>.py` module to this package
and publishes a module-level `TOOLS` sequence of `SimulationTool` objects. A tool
owns one state and may serve several function names, so sibling functions such as
availability, reservation, and cancellation share the same simulated world.
`simulation/kv_demo.py` is the reference shape.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SimulationTool(Protocol):
    """Contract for a resettable, self-contained simulated tool."""

    function_names: tuple[str, ...]

    def initial_state(self) -> Any:
        """Return a fresh state; `reset()` restores exactly this value."""
        ...

    def execute(self, state: Any, function_name: str, arguments: dict[str, Any]) -> Any:
        """Apply one call to `state` in place and return the result payload."""
        ...


class SimulationModuleError(RuntimeError):
    """Raised when a module in this package breaks the `TOOLS` contract."""


def module_names(package_name: str = __name__) -> list[str]:
    """Return the discoverable module names in deterministic (sorted) order."""

    package = importlib.import_module(package_name)
    return sorted(info.name for info in pkgutil.iter_modules(package.__path__) if not info.name.startswith("_"))


def load_tools(package_name: str = __name__) -> tuple[SimulationTool, ...]:
    """Collect the `TOOLS` sequence of every module in `package_name`."""

    tools: list[SimulationTool] = []
    owners: dict[str, str] = {}
    for module_name in module_names(package_name):
        module = importlib.import_module(f"{package_name}.{module_name}")
        published = getattr(module, "TOOLS", None)
        if not isinstance(published, (list, tuple)):
            raise SimulationModuleError(f"{module_name} must publish a module-level TOOLS sequence of simulation tools")
        for tool in published:
            if not isinstance(tool, SimulationTool):
                raise SimulationModuleError(f"{module_name} published a tool that does not satisfy the SimulationTool protocol")
            for function_name in tool.function_names:
                if function_name in owners:
                    raise SimulationModuleError(
                        f"duplicate simulation function '{function_name}': defined in both {owners[function_name]} and {module_name}"
                    )
                owners[function_name] = module_name
            tools.append(tool)
    return tuple(tools)
