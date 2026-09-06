"""URL differential analysis (``urluniq diff old.txt new.txt``).

Compares two URL datasets after normalization:

* NEW      - canonical identities only in the new dataset
* REMOVED  - canonical identities only in the old dataset
* UNCHANGED- identical raw URLs in both
* CHANGED  - same canonical identity, different raw/normalized variants
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from urluniq.core.pipeline import URLPipeline
from urluniq.exceptions import OutputError


@dataclass
class DiffEntry:
    canonical: str
    old_url: str
    new_url: str


@dataclass
class DiffResult:
    new: list[DiffEntry] = field(default_factory=list)
    removed: list[DiffEntry] = field(default_factory=list)
    changed: list[DiffEntry] = field(default_factory=list)
    unchanged: int = 0

    @property
    def unchanged_count(self) -> int:
        return self.unchanged

    def summary_lines(self) -> list[str]:
        return [
            f"New:       {len(self.new)}",
            f"Removed:   {len(self.removed)}",
            f"Unchanged: {self.unchanged}",
            f"Changed:   {len(self.changed)}",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "new": len(self.new),
                "removed": len(self.removed),
                "unchanged": self.unchanged,
                "changed": len(self.changed),
            },
            "new": [e.new_url for e in self.new],
            "removed": [e.old_url for e in self.removed],
            "changed": [
                {"canonical": e.canonical, "old": e.old_url, "new": e.new_url} for e in self.changed
            ],
        }


def compute_diff(
    pipeline: URLPipeline,
    old_urls: list[str],
    new_urls: list[str],
) -> DiffResult:
    """Compute the differential between two raw-URL lists."""
    old_map = _index(pipeline, old_urls)
    new_map = _index(pipeline, new_urls)

    result = DiffResult()
    for canonical, entry in new_map.items():
        old_entry = old_map.get(canonical)
        if old_entry is None:
            result.new.append(DiffEntry(canonical, "", entry.raw))
        elif old_entry.raw == entry.raw:
            result.unchanged += 1
        else:
            result.changed.append(DiffEntry(canonical, old_entry.raw, entry.raw))
    for canonical, entry in old_map.items():
        if canonical not in new_map:
            result.removed.append(DiffEntry(canonical, entry.raw, ""))
    result.new.sort(key=lambda e: e.canonical)
    result.removed.sort(key=lambda e: e.canonical)
    result.changed.sort(key=lambda e: e.canonical)
    return result


@dataclass
class _Indexed:
    raw: str
    normalized: str


def _index(pipeline: URLPipeline, urls: list[str]) -> dict[str, _Indexed]:
    index: dict[str, _Indexed] = {}
    for raw in urls:
        record = pipeline.process(raw)
        if record.error:
            continue
        canonical = record.canonical or record.normalized
        if canonical not in index:
            index[canonical] = _Indexed(record.raw, record.normalized)
    return index


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def export_json(path: Path, result: DiffResult) -> None:
    try:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OutputError(f"cannot write diff export {path}: {exc}") from exc


def export_csv(path: Path, result: DiffResult) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["status", "canonical", "old_url", "new_url"])
            for entry in result.new:
                writer.writerow(["new", entry.canonical, "", entry.new_url])
            for entry in result.removed:
                writer.writerow(["removed", entry.canonical, entry.old_url, ""])
            for entry in result.changed:
                writer.writerow(["changed", entry.canonical, entry.old_url, entry.new_url])
            writer.writerow(["unchanged", "", "", result.unchanged])
    except OSError as exc:
        raise OutputError(f"cannot write diff export {path}: {exc}") from exc


def export_txt(path: Path, result: DiffResult) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            for title, entries, attr in (
                ("NEW URLS", result.new, "new_url"),
                ("REMOVED URLS", result.removed, "old_url"),
            ):
                handle.write(f"{'=' * 12} {title} ({len(entries)}) {'=' * 12}\n")
                for entry in entries:
                    handle.write(f"{getattr(entry, attr)}\n")
            handle.write(
                f"{'=' * 12} MODIFIED/CANONICALIZED URLS ({len(result.changed)}) {'=' * 12}\n"
            )
            for entry in result.changed:
                handle.write(f"- {entry.old_url}\n+ {entry.new_url}\n")
            handle.write(f"{'=' * 12} UNCHANGED ({result.unchanged}) {'=' * 12}\n")
    except OSError as exc:
        raise OutputError(f"cannot write diff export {path}: {exc}") from exc
