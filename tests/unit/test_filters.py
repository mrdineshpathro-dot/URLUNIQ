"""Unit tests for the exclusion / filtering engine."""

from __future__ import annotations

import pytest

from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline
from urluniq.exceptions import ConfigError
from urluniq.filters.engine import FilterEngine


def _pipeline_with(config: Config) -> URLPipeline:
    return URLPipeline(config)


class TestHostFilters:
    def test_include_host(self):
        config = Config()
        config.filters.include_host = ["example.com"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/a").dropped is False
        assert pipeline.process("https://api.example.com/a").dropped is False  # subdomain ok
        assert pipeline.process("https://other.com/a").dropped is True

    def test_exclude_host(self):
        config = Config()
        config.filters.exclude_host = ["ads.example.com"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://ads.example.com/x").dropped is True
        assert pipeline.process("https://example.com/x").dropped is False


class TestExtensionFilters:
    def test_exclude_extension(self):
        config = Config()
        config.filters.exclude_extension = ["jpg", "png"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/a.jpg").dropped is True
        assert pipeline.process("https://example.com/a.PNG").dropped is True
        assert pipeline.process("https://example.com/a.js").dropped is False

    def test_include_extension(self):
        config = Config()
        config.filters.include_extension = ["js"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/a.js").dropped is False
        assert pipeline.process("https://example.com/a.css").dropped is True


class TestPathFilters:
    def test_include_path_substring(self):
        config = Config()
        config.filters.include_path = ["/api/"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/api/v1/x").dropped is False
        assert pipeline.process("https://example.com/web/x").dropped is True

    def test_exclude_path(self):
        config = Config()
        config.filters.exclude_path = ["/wp-admin"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/wp-admin/settings").dropped is True


class TestRegexFilters:
    def test_include_regex(self):
        config = Config()
        config.filters.include_regex = [r"/v\d+/"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/v2/users").dropped is False
        assert pipeline.process("https://example.com/users").dropped is True

    def test_exclude_regex(self):
        config = Config()
        config.filters.exclude_regex = [r"\.(jpg|png)$"]
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/a.jpg").dropped is True
        assert pipeline.process("https://example.com/a.js").dropped is False

    def test_invalid_regex_raises_config_error(self):
        with pytest.raises(ConfigError):
            FilterEngine(Config(), include_regex=["(["])


class TestDomainScope:
    def test_domain_exact(self):
        config = Config()
        config.filters.domain = "example.com"
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://example.com/a").dropped is False
        assert pipeline.process("https://api.example.com/a").dropped is True

    def test_domain_with_subdomains(self):
        config = Config()
        config.filters.domain = "example.com"
        config.filters.include_subdomains = True
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://api.example.com/a").dropped is False
        assert pipeline.process("https://example.com.evil.net/a").dropped is True

    def test_domain_suffix_does_not_leak(self):
        config = Config()
        config.filters.domain = "example.com"
        pipeline = _pipeline_with(config)
        assert pipeline.process("https://notexample.com/a").dropped is True


class TestFilterReasons:
    def test_drop_reason_recorded(self):
        config = Config()
        config.filters.exclude_host = ["x.com"]
        record = URLPipeline(config).process("https://x.com/a")
        assert record.dropped
        assert record.drop_reason == "host excluded"
