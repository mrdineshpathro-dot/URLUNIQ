"""Input registry: format detection, file discovery and stdin support."""

from __future__ import annotations

import fnmatch
import glob
import sys
from collections.abc import Iterator
from pathlib import Path

from urluniq.exceptions import InputError

SUPPORTED_FORMATS = ("txt", "csv", "json", "jsonl")

_FORMAT_BY_SUFFIX = {
    ".txt": "txt",
    ".text": "txt",
    ".list": "txt",
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
}


def detect_format(path: Path) -> str:
    """Detect the input format from a file extension."""
    fmt = _FORMAT_BY_SUFFIX.get(path.suffix.lower())
    if fmt is None:
        return "txt"  # fall back to line-based parsing
    return fmt


def discover_files(
    paths: list[Path] | None = None,
    input_dir: Path | None = None,
    recursive: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Expand files, directories, globs and --input-dir/--recursive rules."""
    files: list[Path] = []
    for path in paths or []:
        if path.is_dir():
            files.extend(_scan_dir(path, recursive, include, exclude))
        elif path.exists():
            files.append(path)
        else:
            # Treat as a glob pattern (e.g. "urls/*.txt").
            matched = sorted(Path(p) for p in sorted(glob.glob(str(path))))
            if not matched:
                raise InputError(f"input not found: {path}")
            files.extend(matched)
    if input_dir is not None:
        if not input_dir.is_dir():
            raise InputError(f"--input-dir is not a directory: {input_dir}")
        files.extend(_scan_dir(input_dir, recursive, include, exclude))
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved not in seen and path.is_file():
            seen.add(resolved)
            unique.append(path)
    return unique


def _scan_dir(
    directory: Path, recursive: bool, include: list[str] | None, exclude: list[str] | None
) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    found: list[Path] = []
    for path in sorted(directory.glob(pattern)):
        if not path.is_file():
            continue
        name = path.name
        if include and not any(fnmatch.fnmatch(name, pat) for pat in include):
            continue
        if exclude and any(fnmatch.fnmatch(name, pat) for pat in exclude):
            continue
        found.append(path)
    return found


def iter_input(
    path: Path | None,
    fmt: str,
    url_column: str | int | None = None,
    json_field: str | None = None,
) -> Iterator[str]:
    """Yield raw URL strings from one source (``None`` means stdin)."""
    if fmt not in SUPPORTED_FORMATS:
        raise InputError(
            f"unsupported input format: {fmt} (choose from {', '.join(SUPPORTED_FORMATS)})"
        )
    if path is None:
        fmt = "txt"  # stdin is always line-based
    if fmt == "csv":
        from urluniq.parsers.csv import iter_csv

        assert path is not None
        yield from iter_csv(path, url_column)
    elif fmt == "json":
        from urluniq.parsers.json import iter_json

        assert path is not None
        yield from iter_json(path, json_field)
    elif fmt == "jsonl":
        from urluniq.parsers.jsonl import iter_jsonl

        assert path is not None
        yield from iter_jsonl(path, json_field)
    else:
        from urluniq.parsers.txt import iter_txt

        yield from iter_txt(path)


def read_stdin_available() -> bool:
    """True when stdin is piped (not a tty)."""
    return not sys.stdin.isatty()
