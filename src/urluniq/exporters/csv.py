"""CSV exporter: url,normalized_url,canonical_url[,category][,changes]."""

from __future__ import annotations

import csv
from typing import IO

from urluniq.models import URLRecord

CSV_FIELDS = ("url", "normalized_url", "canonical_url", "category")


class CSVExporter:
    """Streaming CSV writer for URL records."""

    def __init__(self, handle: IO[str], header: bool = True, explain: bool = False) -> None:
        self.writer = csv.writer(handle, lineterminator="\n")
        self.explain = explain
        self._header_written = False
        if header:
            fields = list(CSV_FIELDS)
            if explain:
                fields.append("changes")
            self.writer.writerow(fields)
            self._header_written = True

    def write(self, record: URLRecord) -> None:
        row = [record.raw, record.normalized, record.canonical, record.category]
        if self.explain:
            row.append("; ".join(record.reasons))
        self.writer.writerow(row)

    def finish(self) -> None:
        """Finalize the output."""
