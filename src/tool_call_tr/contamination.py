"""Cross-corpus contamination checks for isolated benchmark gold records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from tool_call_tr.deduplication import DuplicateReport, SemanticSimilarity, compare_records


BLOCKING_DECISIONS = {"duplicate", "possible_duplicate"}


@dataclass(frozen=True, slots=True)
class ContaminationFinding:
    benchmark_id: str
    dataset_id: str
    decision: str
    signals: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContaminationReport:
    benchmark_records: int
    dataset_records: int
    pairs_checked: int
    findings: tuple[ContaminationFinding, ...]

    @property
    def blocking_count(self) -> int:
        return sum(finding.decision in BLOCKING_DECISIONS for finding in self.findings)

    @property
    def review_required_count(self) -> int:
        return sum(finding.decision == "needs_semantic_review" for finding in self.findings)

    @property
    def status(self) -> str:
        if self.benchmark_records == 0 or self.dataset_records == 0:
            return "blocked"
        if self.blocking_count:
            return "blocked"
        if self.review_required_count:
            return "needs_review"
        return "passed"

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "benchmark_records": self.benchmark_records,
            "dataset_records": self.dataset_records,
            "pairs_checked": self.pairs_checked,
            "blocking_count": self.blocking_count,
            "review_required_count": self.review_required_count,
            "empty_input": self.benchmark_records == 0 or self.dataset_records == 0,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def compare_corpora(
    benchmark_records: Iterable[dict[str, Any]],
    dataset_records: Iterable[dict[str, Any]],
    *,
    semantic: SemanticSimilarity | None = None,
    semantic_threshold: float = 0.9,
) -> ContaminationReport:
    """Compare every benchmark record with every training-dataset record.

    Exact, normalized, provenance, combined query/schema, and optional semantic
    signals are delegated to the existing deterministic duplicate engine.
    """

    benchmark = list(benchmark_records)
    dataset = list(dataset_records)
    findings: list[ContaminationFinding] = []
    for gold in benchmark:
        for training in dataset:
            comparison = compare_records(
                gold,
                training,
                semantic=semantic,
                semantic_threshold=semantic_threshold,
            )
            if comparison.decision != "distinct":
                findings.append(_finding(comparison))
    return ContaminationReport(
        benchmark_records=len(benchmark),
        dataset_records=len(dataset),
        pairs_checked=len(benchmark) * len(dataset),
        findings=tuple(findings),
    )


def _finding(report: DuplicateReport) -> ContaminationFinding:
    signals = report.to_dict()
    benchmark_id = signals.pop("left_id")
    dataset_id = signals.pop("right_id")
    decision = signals.pop("decision")
    return ContaminationFinding(benchmark_id, dataset_id, decision, signals)
