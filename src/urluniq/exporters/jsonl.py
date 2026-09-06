"""JSONL exporter: one structured record per line."""

from __future__ import annotations

import json
from typing import IO

from urluniq.exporters.json import record_to_dict
from urluniq.models import URLRecord


class JSONLExporter:
    """Streaming JSONL writer."""

    def __init__(self, handle: IO[str], explain: bool = False) -> None:
        self.handle = handle
        self.explain = explain

    def write(self, record: URLRecord) -> None:
        self.handle.write(
            json.dumps(record_to_dict(record, self.explain), ensure_ascii=False) + "\n"
        )

    def finish(self) -> None:
        """Finalize the output."""
