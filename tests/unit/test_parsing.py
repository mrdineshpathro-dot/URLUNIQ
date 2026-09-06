"""Unit tests for URL parsing and component helpers."""

from __future__ import annotations

import pytest

from urluniq.core.parser import (
    build_features,
    normalize_ipv4_literal,
    parse_url,
    path_depth,
    path_extension,
    registrable_domain,
    split_path,
    subdomain_of,
)
from urluniq.models import URLRecord


class TestParseUrl:
    def test_basic_components(self):
        parsed, err, _ = parse_url("https://user:pw@Example.COM:8443/a/b/c.js?x=1#frag")
        assert err == ""
        assert parsed is not None
        assert parsed.scheme == "https"
        assert parsed.username == "user"
        assert parsed.password == "pw"
        assert parsed.host == "example.com"
        assert parsed.host_raw == "Example.COM"
        assert parsed.port == 8443
        assert parsed.path == "/a/b/c.js"
        assert parsed.query == "x=1"
        assert parsed.fragment == "frag"
        assert parsed.has_userinfo

    def test_ipv6_brackets_removed(self):
        parsed, err, _ = parse_url("http://[2001:db8::1]:8080/x")
        assert err == ""
        assert parsed is not None
        assert parsed.host == "2001:db8::1"
        assert parsed.is_ipv6
        assert parsed.port == 8080

    def test_whitespace_and_control_noise_cleaned(self):
        parsed, err, reasons = parse_url("  https://example.com/x\u0000  ")
        assert err == ""
        assert parsed is not None
        assert parsed.raw == "https://example.com/x"
        assert "surrounding whitespace removed" in reasons
        assert "control characters removed" in reasons

    def test_empty_url(self):
        parsed, err, _ = parse_url("   ")
        assert parsed is None
        assert err == "empty URL"

    def test_scheme_less_url_rejected(self):
        parsed, err, _ = parse_url("example.com/path")
        assert parsed is None
        assert "invalid URL structure" in err

    def test_too_long_url(self):
        url = "https://example.com/" + "a" * 9000
        parsed, err, _ = parse_url(url)
        assert parsed is None
        assert "maximum length" in err

    def test_idn_flag(self):
        parsed, err, _ = parse_url("https://Bücher.example/path")
        assert err == ""
        assert parsed is not None
        assert parsed.is_idn

    def test_explicit_port_flag(self):
        parsed, err, _ = parse_url("https://example.com/x")
        assert parsed is not None and not parsed.explicit_port
        parsed, _, _ = parse_url("https://example.com:443/x")
        assert parsed is not None and parsed.explicit_port


class TestHelpers:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/a/b/c.js", "js"),
            ("/a/b/", ""),
            ("/", ""),
            ("/.well-known/security", ""),
            ("/archive.tar.GZ", "gz"),
            ("/file.", ""),
            ("/a.b/c", ""),
            ("/index.php", "php"),
        ],
    )
    def test_path_extension(self, path, expected):
        assert path_extension(path) == expected

    @pytest.mark.parametrize(
        ("path", "expected"),
        [("/", 0), ("", 0), ("/a", 1), ("/a/b/c", 3), ("/a//b", 2)],
    )
    def test_path_depth(self, path, expected):
        assert path_depth(path) == expected

    def test_split_path(self):
        assert split_path("/a/b/c.js") == ("/a/b/", "c.js")
        assert split_path("/a/b/") == ("/a/b/", "")
        assert split_path("/") == ("/", "")

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("example.com", "example.com"),
            ("a.b.example.com", "example.com"),
            ("api.example.co.uk", "example.co.uk"),
            ("deep.a.example.com.au", "example.com.au"),
            ("localhost", "localhost"),
            ("127.0.0.1", "127.0.0.1"),
        ],
    )
    def test_registrable_domain(self, host, expected):
        assert registrable_domain(host) == expected

    def test_subdomain_of(self):
        assert subdomain_of("api.example.com") == "api"
        assert subdomain_of("a.b.example.com") == "a.b"
        assert subdomain_of("example.com") == ""
        assert subdomain_of("localhost") == ""

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("2130706433", "127.0.0.1"),
            ("0x7f000001", "127.0.0.1"),
            ("127.1", "127.0.0.1"),
            ("127.0.0.1", "127.0.0.1"),
            ("example.com", "example.com"),
        ],
    )
    def test_normalize_ipv4_literal(self, host, expected):
        assert normalize_ipv4_literal(host) == expected


class TestBuildFeatures:
    def test_feature_fields(self):
        parsed, err, _ = parse_url("https://a.b.example.com:8443/x/y/notes.md?q=1&r=2#top")
        assert parsed is not None
        record = URLRecord(
            raw=parsed.raw,
            normalized="https://a.b.example.com:8443/x/y/notes.md?q=1&r=2",
            canonical="https://a.b.example.com:8443/x/y/notes.md?q=1&r=2",
            category="Document",
            scheme="https",
            host="a.b.example.com",
            subdomain="a.b",
            registrable_domain="example.com",
            path="/x/y/notes.md",
            extension="md",
            param_names=["q", "r"],
            param_count=2,
            has_fragment=True,
            url_length=len(parsed.raw),
            path_depth=3,
        )
        features = build_features(record, parsed)
        data = features.to_dict()
        assert data["directory"] == "/x/y/"
        assert data["filename"] == "notes.md"
        assert data["extension"] == "md"
        assert data["query_param_count"] == 2
        assert data["query_param_names"] == ["q", "r"]
        assert data["has_fragment"] is True
        assert data["url_length"] == len(parsed.raw)
        assert data["path_depth"] == 3
        assert data["category"] == "Document"
        assert data["port"] == 8443
        assert data["registrable_domain"] == "example.com"
