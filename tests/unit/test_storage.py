"""Unit tests for the memory and SQLite storage backends."""

from __future__ import annotations

import sqlite3

from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline
from urluniq.storage.memory import MemoryStore
from urluniq.storage.sqlite import SQLiteStore


def _record(url: str):
    record = URLPipeline(Config()).process(url)
    assert not record.error
    return record


class TestMemoryStore:
    def test_add_and_len(self):
        store = MemoryStore()
        assert store.add("a", _record("https://a.com/")) is True
        assert store.add("a", _record("https://a.com/")) is False
        assert store.add("b", _record("https://b.com/")) is True
        assert len(store) == 2
        assert "a" in store
        assert store.stats() == {"unique": 2}

    def test_preserves_first_seen_order(self):
        store = MemoryStore()
        store.add("z", _record("https://z.com/"))
        store.add("a", _record("https://a.com/"))
        assert [r.host for r in store.records()] == ["z.com", "a.com"]


class TestSQLiteStore:
    def test_schema_and_counts(self, tmp_path):
        path = tmp_path / "u.db"
        store = SQLiteStore(path)
        assert store.unique_count() == 0
        assert store.add("k1", _record("https://example.com/a")) is True
        assert store.add("k1", _record("https://example.com/a")) is False
        assert store.add("k2", _record("https://example.com/b")) is True
        store.commit()
        assert store.unique_count() == 2
        assert store.baseline == 0
        store.close()

        # duplicate_count incremented for k1
        conn = sqlite3.connect(path)
        counts = dict(conn.execute("SELECT hash, duplicate_count FROM urls"))
        conn.close()
        assert counts == {"k1": 2, "k2": 1}

    def test_iter_unique_and_duplicates(self, tmp_path):
        store = SQLiteStore(tmp_path / "u.db")
        store.add("k1", _record("https://example.com/a"))
        store.add("k1", _record("https://example.com/a"))
        store.add("k2", _record("https://example.com/b"))
        store.commit()
        uniques = list(store.iter_unique())
        assert len(uniques) == 2
        assert uniques[0][1] == "https://example.com/a/"
        dups = list(store.iter_duplicates())
        assert dups == [("https://example.com/a/", 2)]
        store.close()

    def test_resume_keeps_existing_rows(self, tmp_path):
        path = tmp_path / "u.db"
        store = SQLiteStore(path)
        store.add("k1", _record("https://example.com/a"))
        store.close()

        resumed = SQLiteStore(path, resume=True)
        assert resumed.baseline == 1
        assert resumed.add("k1", _record("https://example.com/a")) is False
        assert resumed.add("k2", _record("https://example.com/b")) is True
        assert resumed.unique_count() == 2
        resumed.close()

    def test_no_resume_recreates(self, tmp_path):
        path = tmp_path / "u.db"
        store = SQLiteStore(path)
        store.add("k1", _record("https://example.com/a"))
        store.close()
        fresh = SQLiteStore(path, resume=False)
        assert fresh.unique_count() == 0
        fresh.close()

    def test_index_exists(self, tmp_path):
        path = tmp_path / "u.db"
        SQLiteStore(path).close()
        conn = sqlite3.connect(path)
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        conn.close()
        assert any("urls" in name for name, in indexes)
