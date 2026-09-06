"""In-memory deduplication store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from urluniq.models import URLRecord


class MemoryStore:
    """Set/dict based store for datasets that fit into RAM.

    Preserves first-seen order (Python dicts are insertion ordered).
    """

    def __init__(self) -> None:
        self._seen: dict[str, URLRecord] = {}

    def add(self, identity: str, record: URLRecord) -> bool:
        """Return True on first sight of ``identity``."""
        if identity in self._seen:
            return False
        self._seen[identity] = record
        return True

    def __contains__(self, identity: str) -> bool:
        return identity in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def records(self) -> list[URLRecord]:
        """First-seen records in insertion order."""
        return list(self._seen.values())

    def close(self) -> None:  # pragma: no cover - no-op
        """No resources to release."""

    def stats(self) -> dict[str, int]:
        return {"unique": len(self._seen)}
