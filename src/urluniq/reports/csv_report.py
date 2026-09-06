"""CSV report writer (``--report report.csv``).

Emits one ``section,key,value`` row per metric so spreadsheets stay readable
for arbitrarily large Top-N lists.
"""

from __future__ import annotations

import csv
from pathlib import Path

from urluniq.reports.statistics import RunResult

_SUMMARY_ROWS = (
    ("input_urls", "Input URLs"),
    ("valid_urls", "Valid URLs"),
    ("invalid_urls", "Invalid URLs"),
    ("filtered_out", "Filtered URLs"),
    ("duplicates", "Duplicates"),
    ("unique_urls", "Unique URLs"),
    ("normalization_changes", "Normalization changes"),
    ("canonical_changes", "Canonical changes"),
    ("tracking_removed_urls", "Tracking removed (URLs)"),
    ("parameterized_urls", "Parameterized URLs"),
    ("elapsed_seconds", "Processing time (s)"),
)


def write(path: Path, result: RunResult) -> None:
    stats = result.stats
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["section", "key", "value"])
        for key, _label in _SUMMARY_ROWS:
            writer.writerow(["summary", key, getattr(stats, key)])
        for key, count in stats.errors.items():
            writer.writerow(["errors", key, count])
        for label, counter in (
            ("hosts", stats.hosts),
            ("domains", stats.domains),
            ("subdomains", stats.subdomains),
            ("paths", stats.paths),
            ("extensions", stats.extensions),
            ("parameters", stats.params),
            ("categories", stats.categories),
        ):
            for key, count in counter.most_common():
                writer.writerow([label, key, count])
        for meta_key, value in result.metadata.items():
            if meta_key == "configuration":
                continue  # configuration is a nested structure; see JSON report
            writer.writerow(["metadata", meta_key, value])
