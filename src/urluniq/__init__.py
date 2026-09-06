"""URLUNIQ 2.0 - Advanced URL Normalization, Canonicalization & Deduplication.

Use as a Python library::

    from urluniq import normalize_url, canonicalize_url, deduplicate_urls

    result = normalize_url("HTTP://EXAMPLE.COM:80/test/#section")
    print(result)                  # https://example.com/test/
    print(result.changes)          # reasons the URL changed

    clean = deduplicate_urls([...], mode="normalized")

Or from the terminal::

    urluniq clean -i urls.txt -o clean.txt --stats
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from urluniq.config.loader import Config
from urluniq.constants import (
    APP_NAME,
    APP_SUBTITLE,
    APP_TITLE,
    AUTHOR,
    GITHUB_URL,
    PRIMARY_TAGLINE,
    SECONDARY_TAGLINE,
    YOUTUBE_URL,
    __version__,
)
from urluniq.core.parser import parse_url as _parse_components
from urluniq.core.pipeline import URLPipeline
from urluniq.dedupe.engine import DedupeEngine
from urluniq.dedupe.strategies import StrategyContext
from urluniq.models import (
    Backend,
    DedupeMode,
    Features,
    HashAlgorithm,
    OutputFormat,
    ParsedURL,
    Profile,
    URLRecord,
    URLResult,
)
from urluniq.storage.memory import MemoryStore

__all__ = [
    "APP_NAME",
    "APP_SUBTITLE",
    "APP_TITLE",
    "AUTHOR",
    "Backend",
    "Config",
    "DedupeMode",
    "DedupeResult",
    "Features",
    "GITHUB_URL",
    "HashAlgorithm",
    "OutputFormat",
    "ParsedURL",
    "PRIMARY_TAGLINE",
    "Profile",
    "SECONDARY_TAGLINE",
    "URLRecord",
    "URLResult",
    "YOUTUBE_URL",
    "__version__",
    "canonicalize_url",
    "classify_url",
    "deduplicate_urls",
    "normalize_url",
    "parse_url",
]


def _pipeline(profile: str | Profile, config: Any | None) -> URLPipeline:
    from urluniq.config.loader import Config

    cfg = config if isinstance(config, Config) else Config.load()
    return URLPipeline(cfg, profile=profile)


def normalize_url(
    url: str,
    profile: str | Profile = Profile.STANDARD,
    config: Any | None = None,
) -> URLResult:
    """Normalize one URL under ``profile`` (safe/standard/aggressive).

    Returns a :class:`URLResult`; ``str()`` yields the normalized URL and
    ``.changes`` lists the human-readable transformation reasons.
    """
    record = _pipeline(profile, config).process(url)
    return URLResult(
        original=url,
        normalized=record.normalized,
        canonical=record.canonical,
        category=record.category,
        changes=record.reasons,
        error=record.error,
    )


def canonicalize_url(
    url: str,
    profile: str | Profile = Profile.STANDARD,
    config: Any | None = None,
) -> URLResult:
    """Return the canonical identity form of one URL."""
    record = _pipeline(profile, config).process(url)
    return URLResult(
        original=url,
        normalized=record.normalized,
        canonical=record.canonical,
        category=record.category,
        changes=record.reasons,
        error=record.error,
    )


def classify_url(url: str, profile: str | Profile = Profile.STANDARD) -> str:
    """Heuristic classification label for one URL (e.g. ``"API"``)."""
    record = _pipeline(profile, None).process(url)
    return record.category


def parse_url(url: str) -> ParsedURL:
    """Parse a URL into components; raises ``URLValidationError`` if invalid."""
    from urluniq.exceptions import URLValidationError

    parsed, error, _reasons = _parse_components(url)
    if parsed is None or error:
        raise URLValidationError(error or "invalid URL structure")
    return parsed


class DedupeResult:
    """Result of :func:`deduplicate_urls`.

    * ``.urls``      - unique URLs (normalized unless mode is ``exact``)
    * ``.records``   - full :class:`URLRecord` objects for unique URLs
    * ``.invalid``   - ``(url, reason)`` tuples rejected by validation
    * ``.stats``     - simple counter dictionary
    """

    def __init__(
        self,
        records: list[URLRecord],
        invalid: list[tuple[str, str]],
        duplicates: int,
        mode: DedupeMode | str = DedupeMode.NORMALIZED,
    ) -> None:
        self.records = records
        self.invalid = invalid
        self.duplicates = duplicates
        self.mode = DedupeMode(mode)
        self.urls: list[str] = [
            r.raw if self.mode is DedupeMode.EXACT else r.normalized for r in records
        ]

    def __iter__(self):
        return iter(self.urls)

    def __len__(self) -> int:
        return len(self.urls)

    def __getitem__(self, index: int) -> str:
        return self.urls[index]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "input": len(self.records) + len(self.invalid) + self.duplicates,
            "unique": len(self.records),
            "duplicates": self.duplicates,
            "invalid": len(self.invalid),
        }


def deduplicate_urls(
    urls: Iterable[str],
    mode: str | DedupeMode = DedupeMode.NORMALIZED,
    profile: str | Profile = Profile.STANDARD,
    config: Any | None = None,
) -> DedupeResult:
    """Deduplicate an iterable of URLs.

    ``mode`` selects the strategy: exact, normalized, canonical, host, path,
    path_query or smart.
    """
    pipeline = _pipeline(profile, config)
    engine = DedupeEngine(
        store=MemoryStore(),
        mode=mode,
        context=StrategyContext.from_config(pipeline.config),
    )
    unique_records: list[URLRecord] = []
    invalid: list[tuple[str, str]] = []
    duplicates = 0
    for url in urls:
        record = pipeline.process(url)
        if record.error:
            invalid.append((record.raw, record.error))
        elif engine.add(record):
            unique_records.append(record)
        else:
            duplicates += 1
    return DedupeResult(unique_records, invalid, duplicates, mode=engine.mode)
