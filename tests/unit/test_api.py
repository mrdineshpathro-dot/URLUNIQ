"""Unit tests for the public Python library API."""

from __future__ import annotations

import pytest

import urluniq
from urluniq import (
    canonicalize_url,
    classify_url,
    deduplicate_urls,
    normalize_url,
    parse_url,
)
from urluniq.exceptions import URLValidationError
from urluniq.models import URLResult


class TestNormalizeUrl:
    def test_returns_stringlike_result(self):
        result = normalize_url("HTTP://EXAMPLE.COM:80/test/#section")
        assert isinstance(result, URLResult)
        assert str(result) == "http://example.com/test/"
        assert bool(result) is True
        assert result.is_valid

    def test_changes_listed(self):
        result = normalize_url("HTTP://EXAMPLE.COM:80/#f")
        assert "default port removed" in result.changes
        assert "fragment removed" in result.changes

    def test_profiles(self):
        raw = "https://example.com/x#frag"
        assert normalize_url(raw, "safe").normalized.endswith("#frag")
        assert not normalize_url(raw, "standard").normalized.endswith("#frag")

    def test_invalid_url(self):
        result = normalize_url("definitely not a url")
        assert not result.is_valid
        assert result.error
        assert str(result) == ""

    def test_explicit_config_object(self):
        config = urluniq.Config()
        config.normalization.strip_www = True
        result = normalize_url("https://www.example.com/x", config=config)
        assert str(result) == "https://example.com/x/"


class TestCanonicalizeUrl:
    def test_canonical_form(self):
        result = canonicalize_url("https://example.com/s?q=1&utm_source=x")
        assert result.canonical == "https://example.com/s/?q=1"
        assert result.normalized == "https://example.com/s/?q=1&utm_source=x"


class TestClassifyUrl:
    def test_labels(self):
        assert classify_url("https://example.com/api/v1/users") == "API"
        assert classify_url("https://example.com/app.js") == "JS"


class TestParseUrl:
    def test_components(self):
        parsed = parse_url("https://example.com:8443/p?q=1")
        assert parsed.host == "example.com"
        assert parsed.port == 8443

    def test_invalid_raises(self):
        with pytest.raises(URLValidationError):
            parse_url("nope")


class TestDedupeResult:
    def test_container_protocol(self):
        result = deduplicate_urls(["https://a.com/", "https://a.com", "https://b.com/"])
        assert len(result) == 2
        assert list(result) == ["https://a.com/", "https://b.com/"]
        assert result[0] == "https://a.com/"
        assert result.stats == {"input": 3, "unique": 2, "duplicates": 1, "invalid": 0}

    def test_exact_mode_keeps_raw_strings(self):
        result = deduplicate_urls(["https://a.com/", "https://a.com"], mode="exact")
        assert result.urls == ["https://a.com/", "https://a.com"]

    def test_records_available(self):
        result = deduplicate_urls(["https://a.com/x"])
        assert result.records[0].category == "Extensionless"


class TestPackageMetadata:
    def test_version(self):
        assert urluniq.__version__ == "2.0.0"

    def test_branding(self):
        assert urluniq.AUTHOR == "mrdineshpathro-dot"
        assert urluniq.GITHUB_URL == "https://github.com/mrdineshpathro-dot"
        assert urluniq.YOUTUBE_URL == "https://www.youtube.com/@GithubHacker"
        assert urluniq.PRIMARY_TAGLINE == "Normalize. Canonicalize. Deduplicate. Analyze."
