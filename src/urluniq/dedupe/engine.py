"""Deduplication engine combining strategies with storage backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from urluniq.dedupe.hashing import fingerprint
from urluniq.dedupe.strategies import StrategyContext, get_strategy
from urluniq.models import DedupeMode, HashAlgorithm, URLRecord

if TYPE_CHECKING:  # pragma: no cover
    from urluniq.storage.memory import MemoryStore
    from urluniq.storage.sqlite import SQLiteStore


@dataclass(slots=True)
class DuplicateGroup:
    """A duplicate cluster, used by the duplicate-analysis report."""

    key: str
    canonical: str
    variants: list[str] = field(default_factory=list)
    count: int = 0


class DedupeEngine:
    """Decides whether a record is a first occurrence or a duplicate."""

    def __init__(
        self,
        store: MemoryStore | SQLiteStore,
        mode: DedupeMode | str = DedupeMode.NORMALIZED,
        hash_algorithm: HashAlgorithm | str = HashAlgorithm.SHA256,
        use_hash_keys: bool = False,
        context: StrategyContext | None = None,
        collect_duplicates: bool = False,
        max_groups: int = 1000,
        max_variants: int = 50,
    ) -> None:
        self.store = store
        self.mode = DedupeMode(mode)
        self.hash_algorithm = HashAlgorithm(hash_algorithm)
        self.use_hash_keys = use_hash_keys
        self.strategy = get_strategy(self.mode)
        self.context = context or StrategyContext(tracking_params=set())
        self.collect_duplicates = collect_duplicates
        self.max_groups = max_groups
        self.max_variants = max_variants
        self.groups: dict[str, DuplicateGroup] = {}
        self._overflow_groups = 0

    # ------------------------------------------------------------------

    def key_for(self, record: URLRecord) -> str:
        """Compute the raw identity key for a record."""
        return self.strategy(record, self.context)

    def _identity(self, record: URLRecord) -> str:
        key = self.key_for(record)
        if self.use_hash_keys:
            return fingerprint(key, self.hash_algorithm)
        return key

    def add(self, record: URLRecord) -> bool:
        """Register a record; return True when it is a first occurrence."""
        key = self.key_for(record)
        identity = fingerprint(key, self.hash_algorithm) if self.use_hash_keys else key
        first = self.store.add(identity, record)
        if self.collect_duplicates:
            self._track_group(key, record, first)
        return first

    def _track_group(self, key: str, record: URLRecord, first: bool) -> None:
        if first:
            if len(self.groups) < self.max_groups:
                self.groups[key] = DuplicateGroup(
                    key=key,
                    canonical=record.canonical or record.normalized,
                    variants=[record.raw],
                    count=1,
                )
            else:
                self._overflow_groups += 1
            return
        group = self.groups.get(key)
        if group is not None:
            group.count += 1
            if len(group.variants) < self.max_variants:
                group.variants.append(record.raw)

    @property
    def duplicate_groups(self) -> list[DuplicateGroup]:
        """All tracked duplicate groups sorted by size (largest first)."""
        return sorted(self.groups.values(), key=lambda g: (-g.count, g.canonical))

    def commit_store(self) -> None:
        """Flush the backend (no-op for the memory store)."""
        commit = getattr(self.store, "commit", None)
        if callable(commit):
            commit()

    def close(self) -> None:
        """Release backend resources."""
        self.store.close()
