"""JSONL input: one JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from urluniq.exceptions import InputError


def iter_jsonl(path: Path, json_field: str | None = None) -> Iterator[str]:
    """Yield URL strings from a JSONL file (``{"url": "..."}`` per line)."""
    field = json_field or "url"
    try:
        handle = path.open("r", encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc
    try:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                obj: Any = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise InputError(f"invalid JSON on line {line_no} of {path}: {exc}") from exc
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                if field not in obj:
                    raise InputError(
                        f"line {line_no} of {path} has no '{field}' field; use --json-field"
                    )
                yield str(obj[field])
    finally:
        handle.close()
