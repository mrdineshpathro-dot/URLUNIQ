"""CSV input with configurable URL column (``--url-column``)."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from urluniq.exceptions import InputError


def iter_csv(path: Path, url_column: str | int | None = None) -> Iterator[str]:
    """Yield URL strings from a CSV file.

    ``url_column`` may be a header name or a 0-based column index.  When not
    given, the parser uses the ``url`` header if present, otherwise the first
    column.
    """
    try:
        handle = path.open("r", encoding="utf-8-sig", errors="replace", newline="")
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc
    try:
        reader = csv.reader(handle)
        try:
            first_row = next(reader)
        except StopIteration:
            return

        index: int
        if isinstance(url_column, int):
            index = url_column
            if index < len(first_row) and _looks_like_url(first_row[index]):
                # Headerless CSV: the first row already carries data.
                value = first_row[index].strip()
                if value:
                    yield value
        elif url_column is not None:
            try:
                index = first_row.index(url_column)
            except ValueError as exc:
                raise InputError(
                    f"column '{url_column}' not found in {path}; "
                    f"available: {', '.join(first_row)}"
                ) from exc
        elif any(cell.strip().lower() == "url" for cell in first_row):
            index = next(i for i, cell in enumerate(first_row) if cell.strip().lower() == "url")
        else:
            # Headerless CSV: use the first cell that looks like a URL.
            detected = next((i for i, cell in enumerate(first_row) if _looks_like_url(cell)), None)
            if detected is not None:
                index = detected
                yield first_row[index].strip()
            else:
                index = 0

        for row in reader:
            if not row:
                continue
            if index < len(row):
                value = row[index].strip()
                if value:
                    yield value
    finally:
        handle.close()


def _looks_like_url(value: str) -> bool:
    value = value.strip()
    return "://" in value or value.startswith(("http://", "https://", "ftp://"))
