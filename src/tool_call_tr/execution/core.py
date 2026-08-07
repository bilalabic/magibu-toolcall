"""Execution contracts, normalization, routing, and explicit mode transitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
import logging
import time
from typing import Any, Protocol, runtime_checkable

from jsonschema import Draft202012Validator, FormatChecker

from tool_call_tr.registry import ToolRegistry


class ExecutionType(StrEnum):
    REAL_API = "real_api"
    LOCAL_EXECUTABLE = "local_executable"
    SANDBOX = "sandbox"
    MOCK = "mock"
    FULLY_SIMULATED = "fully_simulated"
    NOT_APPLICABLE = "not_applicable"


class ExecutionStatus(StrEnum):
    NOT_CALLED = "not_called"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    EMPTY_RESULT = "empty_result"
    INVALID_RESULT = "invalid_result"


class ExecutionTimeout(RuntimeError):
    pass


class ExecutionRateLimited(RuntimeError):
    pass


class ExecutionRoutingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    call_id: str
    function_name: str
    arguments: dict[str, Any]
    execution_type: ExecutionType
    timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    call_id: str | None
    function_name: str | None
    execution_type: ExecutionType
    status: ExecutionStatus
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    fixture_id: str | None = None
    transition_history: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def no_call(cls) -> "ExecutionResult":
        return cls(None, None, ExecutionType.NOT_APPLICABLE, ExecutionStatus.NOT_CALLED)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["execution_type"] = self.execution_type.value
        value["status"] = self.status.value
        return value


@runtime_checkable
class ExecutionAdapter(Protocol):
    execution_type: ExecutionType

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def reset(self) -> None:
        ...


class ExecutionRouter:
    """Routes only to the explicitly requested mode; it never falls back."""

    def __init__(self, adapters: list[ExecutionAdapter]) -> None:
        self._adapters = {adapter.execution_type: adapter for adapter in adapters}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            adapter = self._adapters[request.execution_type]
        except KeyError as exc:
            raise ExecutionRoutingError(
                f"no adapter registered for requested execution type {request.execution_type.value}; explicit mode transition required"
            ) from exc
        result = adapter.execute(request)
        if result.execution_type != request.execution_type:
            raise ExecutionRoutingError("adapter returned a different execution type; silent fallback is forbidden")
        return result

    def reset(self, execution_type: ExecutionType) -> None:
        try:
            self._adapters[execution_type].reset()
        except KeyError as exc:
            raise ExecutionRoutingError(f"no adapter registered for {execution_type.value}") from exc


class ExecutionEngine:
    def __init__(self, registry: ToolRegistry, router: ExecutionRouter) -> None:
        self.registry = registry
        self.router = router
        self.logger = logging.getLogger("tool_call_tr.execution")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        tool = self.registry.by_function_name(request.function_name)
        Draft202012Validator(tool["function"]["parameters"], format_checker=FormatChecker()).validate(request.arguments)
        if request.execution_type.value not in tool["execution"]["supported_types"]:
            raise ExecutionRoutingError(
                f"{request.execution_type.value} is not declared for {request.function_name}"
            )
        started = time.perf_counter()
        self.logger.info(
            "execution started",
            extra={"event": "execution_started", "execution_type": request.execution_type.value},
        )
        result = self.router.execute(request)
        elapsed = (time.perf_counter() - started) * 1000
        if result.status == ExecutionStatus.PASSED:
            if result.data is None or result.data == [] or result.data == {}:
                result = replace(result, status=ExecutionStatus.EMPTY_RESULT, duration_ms=elapsed)
            else:
                output_errors = list(Draft202012Validator(tool["output_schema"], format_checker=FormatChecker()).iter_errors(result.data))
                if output_errors:
                    result = replace(
                        result,
                        status=ExecutionStatus.INVALID_RESULT,
                        error=output_errors[0].message,
                        duration_ms=elapsed,
                    )
                else:
                    result = replace(result, duration_ms=elapsed)
        else:
            result = replace(result, duration_ms=elapsed)
        self.logger.info(
            "execution finished",
            extra={
                "event": "execution_finished",
                "execution_type": result.execution_type.value,
                "status": result.status.value,
            },
        )
        return result


def transition_execution_mode(
    request: ExecutionRequest,
    to_type: ExecutionType,
    *,
    reason: str,
    transformation_history: list[dict[str, Any]],
    execution_metadata: dict[str, Any] | None = None,
) -> ExecutionRequest:
    if not reason.strip():
        raise ValueError("an explicit execution-mode transition requires a reason")
    transformation_history.append(
        {
            "action": "execution_mode_changed",
            "from_execution_type": request.execution_type.value,
            "to_execution_type": to_type.value,
            "details": reason,
        }
    )
    if execution_metadata is not None:
        execution_metadata["type"] = to_type.value
        execution_metadata["status"] = ExecutionStatus.NOT_CALLED.value
    return replace(request, execution_type=to_type)


def validate_result_transfer(
    prior_result: dict[str, Any],
    next_arguments: dict[str, Any],
    mapping: dict[str, str],
) -> list[str]:
    """Validate declared result-key -> next-argument dependencies."""

    failures: list[str] = []
    for result_key, argument_key in mapping.items():
        if result_key not in prior_result:
            failures.append(f"missing result key: {result_key}")
        elif argument_key not in next_arguments:
            failures.append(f"missing next argument: {argument_key}")
        elif prior_result[result_key] != next_arguments[argument_key]:
            failures.append(f"transfer mismatch: {result_key} -> {argument_key}")
    return failures
