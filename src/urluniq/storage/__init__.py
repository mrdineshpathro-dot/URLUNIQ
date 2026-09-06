"""Storage backends for the deduplication engine."""

from urluniq.storage.memory import MemoryStore
from urluniq.storage.sqlite import SQLiteStore

__all__ = ["MemoryStore", "SQLiteStore"]
