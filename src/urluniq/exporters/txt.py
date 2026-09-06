"""TXT exporter: one URL per line."""

from __future__ import annotations

from collections.abc import Iterable
from typing import IO

from urluniq.models import URLRecord


def txt_lines(records: Iterable[URLRecord], field: str = "normalized") -> Iterable[str]:
    """Render records as plain text lines."""
    for record in records:
        yield (getattr(record, field) or record.raw)


class TXTExporter:
    """Streaming plain-text writer."""

    def __init__(self, handle: IO[str], field: str = "normalized") -> None:
        self.handle = handle
        self.field = field

    def write(self, record: URLRecord) -> None:
        value = getattr(record, self.field) or record.raw
        self.handle.write(value + "\n")

    def finish(self) -> None:  # pragma: no cover - nothing to flush beyond close
        """Finalize the output."""
