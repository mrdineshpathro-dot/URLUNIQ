"""Unit tests for the validation stage."""

from __future__ import annotations

import pytest

from urluniq.core.parser import parse_url
from urluniq.core.validator import Validator


def _reason(url: str, **kwargs) -> str:
    parsed, err, _ = parse_url(url)
    assert parsed is not None, err
    return Validator(**kwargs).validate(parsed)


class TestValidator:
    def test_valid_urls_pass(self):
        for url in (
            "https://example.com/",
            "http://example.com:8080/a",
            "ftp://files.example.com/pub",
            "http://[2001:db8::1]/",
            "http://127.0.0.1/admin",
            "https://xn--bcher-kva.example/",
            "wss://socket.example.com/chat",
        ):
            assert _reason(url) == "", url

    def test_invalid_scheme(self):
        assert "invalid scheme" in _reason("gopher://example.com/x")

    def test_dangerous_schemes_rejected_at_parse_or_validation(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"):
            parsed, err, _ = parse_url(url)
            if parsed is None:
                assert err
            else:
                assert "invalid scheme" in Validator().validate(parsed)

    def test_custom_allowed_schemes(self):
        validator = Validator(allowed_schemes={"http", "https", "gopher"})
        parsed, err, _ = parse_url("gopher://example.com/x")
        assert validator.validate(parsed) == ""

    def test_malformed_host(self):
        assert "malformed hostname" in _reason("http://exa mple.com/")
        assert "malformed hostname" in _reason("http://-bad.example.com/")
        assert "malformed hostname" in _reason("http://bad-.example.com/")
        assert "malformed hostname" in _reason("http://example..com/")

    def test_missing_host(self):
        parsed, err, _ = parse_url("https://:443/x")
        if parsed is not None:  # urlsplit may fail earlier
            assert Validator().validate(parsed) != ""

    def test_bad_port(self):
        # urlsplit rejects out-of-range ports at parse time.
        parsed, err, _ = parse_url("https://example.com:99999/")
        assert parsed is None
        assert "malformed port" in err
        parsed2, err2, _ = parse_url("https://example.com:0/")
        if parsed2 is not None:
            assert "malformed port" in Validator().validate(parsed2)

    def test_invalid_ipv6(self):
        parsed, err, _ = parse_url("http://[2001:zz8::1]/")
        if parsed is None:
            assert "IPv6" in err or "invalid URL structure" in err
        else:
            assert "IPv6" in Validator().validate(parsed)

    def test_trailing_dot_host(self):
        assert "trailing dot" in _reason("https://example.com./x")

    @pytest.mark.parametrize("scheme", ["http", "https", "ws", "wss", "ftp", "ftps"])
    def test_all_default_schemes_accepted(self, scheme):
        assert _reason(f"{scheme}://example.com/") == ""
