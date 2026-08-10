"""Validate repository-owned contribution contracts for CI and local use."""

from pathlib import Path
import sys

from tool_call_tr.contribution_review import review_contribution


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = review_contribution(Path.cwd())
    print(report.markdown())
    return int(report.has_errors)


if __name__ == "__main__":
    raise SystemExit(main())
