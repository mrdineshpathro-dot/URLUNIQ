"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakeStdin(io.StringIO):
    """StringIO that reports itself as a pipe (not a tty)."""

    def isatty(self) -> bool:  # noqa: D102
        return False


class FakeTty(io.StringIO):
    """StringIO that reports itself as an interactive terminal."""

    def isatty(self) -> bool:  # noqa: D102
        return True


@pytest.fixture
def sample_urls() -> list[str]:
    return [
        "HTTP://EXAMPLE.COM:80/",
        "http://example.com",
        "https://EXAMPLE.com/",
        "https://example.com/#home",
        "https://example.com",
        "https://example.com/search?q=1&utm_source=test",
        "https://example.com/search?utm_source=test&q=1",
        "https://example.com/search?q=1",
    ]


@pytest.fixture
def urls_file(tmp_path: Path, sample_urls: list[str]) -> Path:
    path = tmp_path / "urls.txt"
    path.write_text("\n".join(sample_urls) + "\n", encoding="utf-8")
    return path
