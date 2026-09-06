"""Unit tests for deduplication strategies, engine and hashing."""

from __future__ import annotations

import pytest

from urluniq import deduplicate_urls
from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline
from urluniq.dedupe.engine import DedupeEngine
from urluniq.dedupe.hashing import fingerprint
from urluniq.dedupe.strategies import StrategyContext, available_modes, get_strategy
from urluniq.exceptions import ConfigError
from urluniq.models import DedupeMode, HashAlgorithm
from urluniq.storage.memory import MemoryStore


def _records(urls: list[str]) -> list:
    pipeline = URLPipeline(Config())
    return [pipeline.process(url) for url in urls]


class TestStrategies:
    URLs = [
        "https://example.com/a?utm_source=x&q=1",
        "https://example.com/a?q=1",
        "https://example.com/b",
        "https://other.example.com/a?q=1",
        "https://example.com/C/",
    ]

    def test_exact(self):
        records = _records(self.URLs)
        ctx = StrategyContext(tracking_params=set())
        keys = [get_strategy(DedupeMode.EXACT)(r, ctx) for r in records]
        assert keys[0] != keys[1]

    def test_normalized_collapses_casing(self):
        records = _records(["http://EXAMPLE.com/A", "http://example.com/A/"])
        ctx = StrategyContext(tracking_params=set())
        keys = {get_strategy(DedupeMode.NORMALIZED)(r, ctx) for r in records}
        assert keys == {"http://example.com/A/"}

    def test_canonical_collapses_tracking(self):
        records = _records(self.URLs[:2])
        ctx = StrategyContext(tracking_params=set())
        keys = {get_strategy(DedupeMode.CANONICAL)(r, ctx) for r in records}
        assert len(keys) == 1

    def test_host(self):
        records = _records(self.URLs)
        ctx = StrategyContext(tracking_params=set())
        keys = {get_strategy(DedupeMode.HOST)(r, ctx) for r in records}
        assert keys == {"example.com", "other.example.com"}

    def test_path(self):
        records = _records(self.URLs)
        ctx = StrategyContext(tracking_params=set())
        keys = [get_strategy(DedupeMode.PATH)(r, ctx) for r in records]
        assert len(set(keys)) == 4  # /a/, /b/, other-host /a/, /C/

    def test_path_query(self):
        records = _records(self.URLs)
        # With no tracking set configured, utm_source is significant -> 5 keys.
        ctx = StrategyContext(tracking_params=set())
        keys = [get_strategy(DedupeMode.PATH_QUERY)(r, ctx) for r in records]
        assert len(set(keys)) == 5
        # With tracking configured, /a variants collapse -> 4 keys.
        ctx_tracking = StrategyContext(tracking_params={"utm_source"})
        keys = [get_strategy(DedupeMode.PATH_QUERY)(r, ctx_tracking) for r in records]
        assert len(set(keys)) == 4

    def test_smart_ignores_tracking_and_session(self):
        records = _records(
            [
                "https://example.com/p?q=1&utm_source=x",
                "https://example.com/p?q=1",
                "https://example.com/p?q=1&jsessionid=ABC",
            ]
        )
        ctx = StrategyContext(tracking_params={"utm_source"})
        keys = {get_strategy(DedupeMode.SMART)(r, ctx) for r in records}
        assert len(keys) == 1

    def test_smart_distinguishes_significant_values(self):
        records = _records(["https://example.com/search?q=1", "https://example.com/search?q=2"])
        ctx = StrategyContext(tracking_params=set())
        keys = {get_strategy(DedupeMode.SMART)(r, ctx) for r in records}
        assert len(keys) == 2

    def test_available_modes(self):
        assert available_modes() == [
            "exact",
            "normalized",
            "canonical",
            "host",
            "path",
            "path_query",
            "smart",
        ]


class TestEngine:
    def test_first_occurrence_wins(self):
        pipeline = URLPipeline(Config())
        engine = DedupeEngine(store=MemoryStore(), mode=DedupeMode.NORMALIZED)
        first = pipeline.process("http://A.com/x")
        second = pipeline.process("http://a.com/x/")
        third = pipeline.process("http://a.com/y")
        assert engine.add(first) is True
        assert engine.add(second) is False
        assert engine.add(third) is True
        assert len(engine.store) == 2

    def test_duplicate_group_collection(self):
        pipeline = URLPipeline(Config())
        engine = DedupeEngine(
            store=MemoryStore(),
            mode=DedupeMode.CANONICAL,  # canonical identity merges http/https
            collect_duplicates=True,
        )
        for url in (
            "http://EXAMPLE.com/login/",
            "http://example.com/login",
            "https://example.com:443/login",
            "https://example.com/login#section",
        ):
            engine.add(pipeline.process(url))
        groups = engine.duplicate_groups
        assert len(groups) == 1
        assert groups[0].count == 4
        assert groups[0].canonical == "https://example.com/login/"
        assert len(groups[0].variants) == 4

    def test_hash_keys_opt_in(self):
        engine = DedupeEngine(
            store=MemoryStore(),
            mode=DedupeMode.NORMALIZED,
            hash_algorithm=HashAlgorithm.MD5,
            use_hash_keys=True,
        )
        record = _records(["https://example.com/"])[0]
        engine.add(record)
        key = engine.key_for(record)
        from urluniq.dedupe.hashing import fingerprint as fp

        assert engine.store.__contains__(fp(key, HashAlgorithm.MD5))


class TestHashing:
    @pytest.mark.parametrize(
        ("algorithm", "length"),
        [(HashAlgorithm.SHA256, 64), (HashAlgorithm.SHA1, 40), (HashAlgorithm.MD5, 32)],
    )
    def test_fingerprint_lengths(self, algorithm, length):
        digest = fingerprint("https://example.com", algorithm)
        assert len(digest) == length
        assert digest == fingerprint("https://example.com", algorithm)

    def test_xxhash_without_package_raises(self):
        try:
            import xxhash  # noqa: F401

            assert len(fingerprint("x", "xxhash")) >= 16
        except ImportError:
            with pytest.raises(ConfigError):
                fingerprint("x", HashAlgorithm.XXHASH)


class TestLibraryDedupe:
    def test_deduplicate_urls_modes(self):
        urls = [
            "http://EXAMPLE.com:80/a",
            "http://example.com/a",
            "https://example.com/b?x=1",
            "https://example.com/b?x=2",
        ]
        normalized = deduplicate_urls(urls, mode="normalized")
        assert len(normalized) == 3
        canonical = deduplicate_urls(urls, mode="canonical")
        assert len(canonical) == 3
        host = deduplicate_urls(urls, mode="host")
        assert host.urls == ["http://example.com/a/"]
        exact = deduplicate_urls(urls, mode="exact")
        assert len(exact) == 4
        path = deduplicate_urls(urls, mode="path")
        assert len(path) == 2

    def test_invalid_urls_reported(self):
        result = deduplicate_urls(["https://example.com/", "not a url", "://x"])
        assert result.stats["unique"] == 1
        assert result.stats["invalid"] == 2
        assert result.invalid[0][0] == "not a url"
