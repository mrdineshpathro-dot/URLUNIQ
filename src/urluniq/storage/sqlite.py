"""Persistent SQLite deduplication backend for extremely large datasets.

Schema lives in a single ``urls`` table with a PRIMARY KEY on the identity
hash so lookups stay O(log n) via the implicit index.  ``--resume`` keeps the
database between runs so interrupted processing can continue.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from urluniq.exceptions import BackendError

if TYPE_CHECKING:  # pragma: no cover
    from urluniq.models import URLRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    hash            TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    normalized_url  TEXT,
    canonical_url   TEXT,
    category        TEXT,
    first_seen      REAL NOT NULL,
    duplicate_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls (normalized_url);
"""


class SQLiteStore:
    """SQLite-backed identity store."""

    def __init__(self, path: str, resume: bool = False) -> None:
        self.path = path
        try:
            if not resume and os.path.exists(path):
                os.remove(path)
                for suffix in ("-wal", "-shm"):
                    side = Path(str(path) + suffix)
                    if side.exists():
                        os.remove(side)
            self.conn = sqlite3.connect(path)
            self.conn.executescript(_SCHEMA)
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        except sqlite3.Error as exc:
            raise BackendError(f"sqlite backend failed: {exc}") from exc
        self._baseline = self.unique_count()

    # ------------------------------------------------------------------

    def add(self, identity: str, record: URLRecord) -> bool:
        """Insert the identity; return True on first occurrence."""
        try:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO urls"
                " (hash, url, normalized_url, canonical_url, category, first_seen)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    identity,
                    record.raw,
                    record.normalized,
                    record.canonical,
                    record.category,
                    time.time(),
                ),
            )
            if cur.rowcount == 1:
                return True
            self.conn.execute(
                "UPDATE urls SET duplicate_count = duplicate_count + 1 WHERE hash = ?",
                (identity,),
            )
            return False
        except sqlite3.Error as exc:
            raise BackendError(f"sqlite insert failed: {exc}") from exc

    def unique_count(self) -> int:
        """Number of unique identities currently stored."""
        cur = self.conn.execute("SELECT COUNT(*) FROM urls")
        return int(cur.fetchone()[0])

    @property
    def baseline(self) -> int:
        """Unique rows already present when the store was opened."""
        return self._baseline

    def commit(self) -> None:
        self.conn.commit()

    def iter_unique(self) -> Iterator[tuple[str, str, str, str]]:
        """Yield ``(url, normalized, canonical, category)`` for unique rows."""
        cur = self.conn.execute(
            "SELECT url, normalized_url, canonical_url, category FROM urls" " ORDER BY first_seen"
        )
        for row in cur:
            yield row[0], row[1], row[2], row[3]

    def iter_duplicates(self) -> Iterator[tuple[str, int]]:
        """Yield ``(canonical_url, duplicate_count)`` for duplicated rows."""
        cur = self.conn.execute(
            "SELECT COALESCE(NULLIF(canonical_url,''), normalized_url, url),"
            " duplicate_count FROM urls WHERE duplicate_count > 1"
            " ORDER BY duplicate_count DESC"
        )
        for row in cur:
            yield row[0], int(row[1])

    def close(self) -> None:
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error:  # pragma: no cover - best effort
            pass

    def stats(self) -> dict[str, int]:
        return {"unique": self.unique_count(), "baseline": self._baseline}
