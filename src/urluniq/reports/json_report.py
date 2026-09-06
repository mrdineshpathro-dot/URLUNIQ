"""JSON report writer (``--report report.json``)."""

from __future__ import annotations

import json
from pathlib import Path

from urluniq.reports.statistics import RunResult


def write(path: Path, result: RunResult) -> None:
    """Write the full run result as a reproducible JSON report."""
    path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
