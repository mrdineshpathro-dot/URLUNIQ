"""JSON input: an array of URLs/objects, or a single object with a list."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from urluniq.exceptions import InputError


def iter_json(path: Path, json_field: str | None = None) -> Iterator[str]:
    """Yield URL strings from a JSON document.

    Accepts:
    * ``["https://a", "https://b"]``
    * ``[{"url": "...", ...}, ...]`` (field name from ``json_field`` or ``url``)
    * ``{"urls": [...]}`` / ``{"url": "..."}`` style objects
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {path}: {exc}") from exc
    yield from _iter_value(data, json_field, path)


def _iter_value(data: Any, json_field: str | None, path: Path, _depth: int = 0) -> Iterator[str]:
    if _depth > 3:
        return
    field = json_field or "url"
    if isinstance(data, str):
        if data.strip():
            yield data.strip()
    elif isinstance(data, list):
        for item in data:
            yield from _iter_value(item, json_field, path, _depth + 1)
    elif isinstance(data, dict):
        if field in data:
            yield from _iter_value(data[field], json_field, path, _depth + 1)
        elif "urls" in data and isinstance(data["urls"], list):
            for item in data["urls"]:
                yield from _iter_value(item, json_field, path, _depth + 1)
        else:
            raise InputError(f"JSON object in {path} has no '{field}' field; use --json-field")
