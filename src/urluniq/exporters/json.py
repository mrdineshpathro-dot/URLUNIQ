"""JSON exporter: a single structured array."""

from __future__ import annotations

import json
from typing import IO, Any

from urluniq.models import URLRecord


def record_to_dict(record: URLRecord, explain: bool = False) -> dict[str, Any]:
    """Serialize one record to the documented JSON shape."""
    obj: dict[str, Any] = {
        "url": record.raw,
        "normalized_url": record.normalized,
        "canonical_url": record.canonical,
        "category": record.category,
    }
    if explain:
        obj["changes"] = record.reasons
    return obj


class JSONExporter:
    """Buffering JSON array writer (JSONL is the streaming alternative)."""

    def __init__(self, handle: IO[str], explain: bool = False) -> None:
        self.handle = handle
        self.explain = explain
        self._records: list[dict[str, Any]] = []
        self._count = 0

    def write(self, record: URLRecord) -> None:
        self._records.append(record_to_dict(record, self.explain))
        self._count += 1
        # Guard memory: flush in document batches of 100k records.
        if self._count >= 100_000:
            self._flush_partial()

    def _flush_partial(self) -> None:  # pragma: no cover - large datasets only
        json.dump(self._records, self.handle)
        self.handle.write("\n")
        self._records = []
        self._count = 0

    def finish(self) -> None:
        json.dump(self._records, self.handle, indent=2)
        self.handle.write("\n")
        self._records = []
        self._count = 0
