"""Stable diagnostics shared by validators and the CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str = "$"
    severity: Severity = Severity.ERROR
    record_id: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["severity"] = self.severity.value
        return value


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue]
    records_checked: int = 0

    @property
    def valid(self) -> bool:
        return not any(issue.severity == Severity.ERROR for issue in self.issues)

    def extend(self, issues: list[ValidationIssue]) -> None:
        self.issues.extend(issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "records_checked": self.records_checked,
            "error_count": sum(issue.severity == Severity.ERROR for issue in self.issues),
            "warning_count": sum(issue.severity == Severity.WARNING for issue in self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def human(self) -> str:
        if not self.issues:
            return f"OK: {self.records_checked} record(s) validated"
        lines: list[str] = []
        for issue in self.issues:
            location = issue.path
            if issue.line is not None:
                location += f" line={issue.line}"
            if issue.record_id:
                location += f" record={issue.record_id}"
            lines.append(f"{issue.severity.value.upper()} {issue.code} {location}: {issue.message}")
        return "\n".join(lines)

