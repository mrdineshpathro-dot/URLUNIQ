"""Plain-text input: one URL per line.  Blank lines and ``#`` comments skip."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

from urluniq.exceptions import InputError


def iter_txt(path: Path | None) -> Iterator[str]:
    """Yield raw URL lines from a text file, or stdin when path is None."""
    handle = sys.stdin if path is None else _open(path)
    try:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield stripped
    finally:
        if handle is not sys.stdin:
            handle.close()


def _open(path: Path):
    try:
        return path.open("r", encoding="utf-8-sig", errors="replace", buffering=1024 * 512)
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc
