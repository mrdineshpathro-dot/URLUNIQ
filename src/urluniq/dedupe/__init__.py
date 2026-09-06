"""Deduplication package: engine, strategies and hashing."""

from urluniq.dedupe.engine import DedupeEngine, DuplicateGroup
from urluniq.dedupe.hashing import fingerprint
from urluniq.dedupe.strategies import StrategyContext, available_modes, get_strategy

__all__ = [
    "DedupeEngine",
    "DuplicateGroup",
    "StrategyContext",
    "available_modes",
    "fingerprint",
    "get_strategy",
]
