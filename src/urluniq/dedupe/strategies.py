"""Deduplication key strategies.

Each strategy derives the comparison key for one URL record.  Keys are plain
strings; the engine optionally fingerprints them (see ``dedupe/hashing.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote

from urluniq.config.loader import Config
from urluniq.constants import SESSION_PARAM_HINTS
from urluniq.models import DedupeMode, URLRecord
from urluniq.normalizers.query import split_pairs


@dataclass(slots=True)
class StrategyContext:
    """Configuration needed by parameter-aware strategies."""

    tracking_params: set[str]
    case_sensitive_names: bool = False
    smart_ignore_tracking: bool = True
    smart_ignore_session: bool = True
    smart_ignore_empty: bool = True

    @classmethod
    def from_config(cls, config: Config) -> StrategyContext:
        return cls(
            tracking_params=config.tracking_params(),
            case_sensitive_names=config.query.case_sensitive_names,
            smart_ignore_tracking=config.dedupe.smart_ignore_tracking,
            smart_ignore_session=config.dedupe.smart_ignore_session,
            smart_ignore_empty=config.dedupe.smart_ignore_empty,
        )


def _significant_params(record: URLRecord, ctx: StrategyContext) -> list[str]:
    """Query pairs reduced to the parameters that carry identity.

    Drops tracking parameters, likely session/state parameters and empty
    values according to the smart-dedupe configuration.
    """
    significant: list[str] = []
    for pair in split_pairs(record.query):
        raw_name = pair[0]
        name = unquote(raw_name)
        cmp_name = name if ctx.case_sensitive_names else name.lower()
        value = pair[1] if len(pair) == 2 else ""
        if ctx.smart_ignore_tracking and cmp_name in ctx.tracking_params:
            continue
        if ctx.smart_ignore_session and any(h in cmp_name for h in SESSION_PARAM_HINTS):
            continue
        if ctx.smart_ignore_empty and value == "":
            continue
        significant.append(f"{cmp_name}={unquote(value)}")
    significant.sort()
    return significant


def exact_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Identity: raw string."""
    return record.raw


def normalized_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Identity: normalized URL."""
    return record.normalized or record.raw


def canonical_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Identity: canonical URL."""
    return record.canonical or record.normalized or record.raw


def host_key(record: URLRecord, ctx: StrategyContext) -> str:
    """One representative URL per host."""
    return record.host


def path_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Hostname + path."""
    return f"{record.host}|{record.path}"


def path_query_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Hostname + path + meaningful query parameters."""
    params = "&".join(_significant_params(record, ctx))
    return f"{record.host}|{record.path}|{params}"


def smart_key(record: URLRecord, ctx: StrategyContext) -> str:
    """Configurable rules: scheme+host+path plus *significant* parameters.

    Volatile query noise (tracking, session/state and empty parameters) is
    ignored so the same endpoint with different trackers collapses.
    """
    params = "&".join(_significant_params(record, ctx))
    return f"{record.scheme}://{record.host}|{record.path}|{params}"


_STRATEGIES = {
    DedupeMode.EXACT: exact_key,
    DedupeMode.NORMALIZED: normalized_key,
    DedupeMode.CANONICAL: canonical_key,
    DedupeMode.HOST: host_key,
    DedupeMode.PATH: path_key,
    DedupeMode.PATH_QUERY: path_query_key,
    DedupeMode.SMART: smart_key,
}


def get_strategy(mode: DedupeMode | str):
    """Return the key function for ``mode``."""
    mode = DedupeMode(mode)
    return _STRATEGIES[mode]


def available_modes() -> list[str]:
    """All supported dedupe mode names."""
    return [mode.value for mode in DedupeMode]
