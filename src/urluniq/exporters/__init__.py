"""Exporter registry."""

from __future__ import annotations

from typing import IO

from urluniq.exceptions import ConfigError
from urluniq.exporters.csv import CSVExporter
from urluniq.exporters.json import JSONExporter
from urluniq.exporters.jsonl import JSONLExporter
from urluniq.exporters.txt import TXTExporter
from urluniq.models import OutputFormat


def build_exporter(
    fmt: OutputFormat | str,
    handle: IO[str],
    csv_header: bool = True,
    explain: bool = False,
    txt_field: str = "normalized",
) -> TXTExporter | CSVExporter | JSONExporter | JSONLExporter:
    """Create the exporter for an output format."""
    try:
        fmt = OutputFormat(fmt)
    except ValueError as exc:
        raise ConfigError(f"unknown output format: {fmt}") from exc
    if fmt is OutputFormat.TXT:
        return TXTExporter(handle, field=txt_field)
    if fmt is OutputFormat.CSV:
        return CSVExporter(handle, header=csv_header, explain=explain)
    if fmt is OutputFormat.JSON:
        return JSONExporter(handle, explain=explain)
    return JSONLExporter(handle, explain=explain)


__all__ = ["build_exporter", "TXTExporter", "CSVExporter", "JSONExporter", "JSONLExporter"]
