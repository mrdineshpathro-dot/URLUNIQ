"""Unit tests for normalization: every feature listed in the spec."""

from __future__ import annotations

import pytest

from urluniq import normalize_url
from urluniq.config.loader import Config
from urluniq.constants import PATH_SAFE_RAW, QUERY_SAFE_RAW
from urluniq.normalizers import build_canonicalizer, build_normalizer
from urluniq.normalizers.base import (
    collapse_duplicate_slashes,
    normalize_percent_encoding,
    remove_dot_segments,
)


def _n(url: str, profile: str = "standard", **overrides):
    config = Config()
    for key, value in overrides.items():
        setattr(config.normalization, key, value)
    return normalize_url(url, profile=profile, config=config)


class TestPathHelpers:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/a/b/c/../../d/./e", "/a/d/e"),
            ("/a/../..", "/"),
            ("/a/b/", "/a/b/"),
            ("/../x", "/x"),
            ("/no/dots", "/no/dots"),
        ],
    )
    def test_remove_dot_segments(self, path, expected):
        assert remove_dot_segments(path) == expected

    def test_collapse_slashes(self):
        assert collapse_duplicate_slashes("//a///b//") == "/a/b/"
        assert collapse_duplicate_slashes("/a/b") == "/a/b"


class TestPercentEncoding:
    def test_unreserved_decoded(self):
        assert normalize_percent_encoding("%7Etilde~%2D", set()) == "~tilde~-"

    def test_reserved_stays_encoded_uppercase(self):
        assert normalize_percent_encoding("%2f%3f", set()) == "%2F%3F"

    def test_lowercase_hex_normalized(self):
        assert normalize_percent_encoding("%2f", set()) == "%2F"

    def test_space_encoded(self):
        assert normalize_percent_encoding("a b", PATH_SAFE_RAW) == "a%20b"

    def test_non_ascii_encoded(self):
        assert normalize_percent_encoding("café", PATH_SAFE_RAW) == "caf%C3%A9"

    def test_literal_percent_encoded(self):
        assert normalize_percent_encoding("50%", PATH_SAFE_RAW) == "50%25"

    def test_raw_safe_chars_untouched(self):
        assert normalize_percent_encoding("/a=b;c,d", PATH_SAFE_RAW) == "/a=b;c,d"

    def test_query_plus_untouched(self):
        assert normalize_percent_encoding("a+b", QUERY_SAFE_RAW) == "a+b"


class TestSafeProfile:
    def test_safe_keeps_structure(self):
        # Safe lowercases scheme/host only; ports, dot segments, fragments
        # and query ordering are all preserved.
        result = _n("HTTP://EXAMPLE.com:80/a/../b/?z=1&a=2#frag", "safe")
        assert result.normalized == "http://example.com:80/a/../b/?z=1&a=2#frag"

    def test_safe_still_lowercases_scheme_and_host(self):
        result = _n("HTTP://EXAMPLE.com/", "safe")
        assert result.normalized == "http://example.com/"


class TestStandardProfile:
    def test_scheme_and_host_lowercased(self):
        r = _n("HTTP://EXAMPLE.COM/", "standard")
        assert r.normalized == "http://example.com/"
        assert "hostname lowercased" in r.changes

    def test_default_port_removed(self):
        r = _n("http://example.com:80/x", "standard")
        assert r.normalized == "http://example.com/x/"
        assert "default port removed" in r.changes

    def test_nondefault_port_kept(self):
        assert _n("http://example.com:8080/x").normalized == "http://example.com:8080/x/"

    def test_empty_path_expanded(self):
        r = _n("http://example.com", "standard")
        assert r.normalized == "http://example.com/"
        assert "empty path expanded to '/'" in r.changes

    def test_fragment_removed(self):
        r = _n("https://example.com/#home", "standard")
        assert r.normalized == "https://example.com/"
        assert "fragment removed" in r.changes

    def test_trailing_slash_added_for_extensionless(self):
        r = _n("https://example.com/search", "standard")
        assert r.normalized == "https://example.com/search/"
        assert "trailing slash added" in r.changes

    def test_trailing_slash_kept_for_files(self):
        assert (
            _n("https://example.com/app.js", "standard").normalized == "https://example.com/app.js"
        )
        r = _n("https://example.com/app.js/", "standard")
        assert r.normalized == "https://example.com/app.js"
        assert "trailing slash removed" in r.changes

    def test_duplicate_slashes_collapsed(self):
        r = _n("https://example.com//a///b", "standard")
        assert r.normalized == "https://example.com/a/b/"
        assert "duplicate slashes collapsed" in r.changes

    def test_dot_segments_resolved(self):
        r = _n("https://example.com/a/./b/../c", "standard")
        assert r.normalized == "https://example.com/a/c/"
        assert "dot segments removed" in r.changes

    def test_query_sorted(self):
        r = _n("https://example.com/p?b=2&a=1", "standard")
        assert r.normalized == "https://example.com/p/?a=1&b=2"
        assert "query parameters sorted" in r.changes

    def test_query_duplicates_preserved_in_standard(self):
        assert _n("https://example.com/p?a=1&a=2").normalized == "https://example.com/p/?a=1&a=2"

    def test_idn_to_punycode(self):
        r = _n("https://Bücher.example/x", "standard")
        assert r.normalized == "https://xn--bcher-kva.example/x/"
        assert "punycode" in " ".join(r.changes).lower()

    def test_ipv4_alternative_forms(self):
        assert _n("http://2130706433/admin").normalized == "http://127.0.0.1/admin/"
        assert _n("http://0x7f000001/admin").normalized == "http://127.0.0.1/admin/"

    def test_ipv6_compressed(self):
        r = _n("http://[2001:0db8:0000:0000:0000:0000:0000:0001]/x", "standard")
        assert r.normalized == "http://[2001:db8::1]/x/"

    def test_userinfo_preserved(self):
        assert _n("http://user:pw@example.com/x").normalized == "http://user:pw@example.com/x/"

    def test_userinfo_redaction_option(self):
        config = Config()
        norm = build_normalizer("standard", config, redact_userinfo=True)
        from urluniq.core.parser import parse_url

        parsed, err, _ = parse_url("http://user:pw@example.com/x")
        result = norm.apply(parsed)
        assert result.url == "http://[REDACTED]@example.com/x/"
        assert "credentials redacted" in result.reasons

    def test_percent_encoding_normalized(self):
        r = _n("https://example.com/%7Euser/%2Fpath%20name", "standard")
        assert r.normalized == "https://example.com/~user/%2Fpath%20name/"

    def test_w3c_example(self):
        result = normalize_url("HTTP://EXAMPLE.COM:80/test/#section")
        assert str(result) == "http://example.com/test/"

    def test_upgrade_http_opt_in(self):
        assert _n("http://example.com/x", "aggressive").normalized == "http://example.com/x/"
        r = _n("http://example.com/x", "aggressive", upgrade_http=True)
        assert r.normalized == "https://example.com/x/"

    def test_strip_www_opt_in(self):
        assert _n("https://www.example.com/x").normalized == "https://www.example.com/x/"
        r = _n("https://www.example.com/x", "aggressive", strip_www=True)
        assert r.normalized == "https://example.com/x/"

    def test_remove_port_option(self):
        config = Config()
        config.normalization.remove_port = True
        result = normalize_url("http://example.com:8080/x", config=config)
        assert str(result) == "http://example.com/x/"


class TestAggressiveProfile:
    def test_tracking_removed_by_default(self):
        r = _n("https://example.com/s?q=1&utm_source=x&fbclid=abc", "aggressive")
        assert r.normalized == "https://example.com/s/?q=1"
        assert "tracking parameters removed" in r.changes

    def test_duplicate_params_removed(self):
        r = _n("https://example.com/p?id=1&id=2", "aggressive")
        assert r.normalized == "https://example.com/p/?id=1"
        assert "duplicate query parameters removed" in r.changes

    def test_index_document_stripped(self):
        r = _n("https://example.com/docs/index.html", "aggressive")
        assert r.normalized == "https://example.com/docs/"
        assert "default index document removed" in r.changes


class TestCanonicalizer:
    def _canon(self, url: str) -> str:
        config = Config()
        canon = build_canonicalizer(config)
        from urluniq.core.parser import parse_url

        parsed, err, _ = parse_url(url)
        assert parsed is not None
        return canon.apply(parsed).url

    def test_canonical_removes_tracking(self):
        assert self._canon("https://example.com/s?q=1&utm_source=x") == "https://example.com/s/?q=1"

    def test_canonical_sorts_and_dedupes(self):
        assert self._canon("https://example.com/p?b=2&a=1&a=1") == "https://example.com/p/?a=1&b=2"

    def test_canonical_upgrades_scheme_by_default(self):
        # The canonical identity merges http/https variants (spec section 12).
        assert self._canon("http://example.com/x") == "https://example.com/x/"

    def test_scheme_upgrade_can_be_disabled(self):
        config = Config()
        config.canonicalization["upgrade_http"] = False
        canon = build_canonicalizer(config)
        from urluniq.core.parser import parse_url

        parsed, _, _ = parse_url("http://example.com/x")
        assert canon.apply(parsed).url == "http://example.com/x/"

    def test_tracking_override_via_config(self):
        config = Config()
        config.canonicalization["remove_tracking_params"] = False
        canon = build_canonicalizer(config)
        from urluniq.core.parser import parse_url

        parsed, _, _ = parse_url("https://example.com/s?q=1&utm_source=x")
        assert canon.apply(parsed).url == "https://example.com/s/?q=1&utm_source=x"


class TestNormalizationConfigMerge:
    def test_user_global_overrides_apply_to_profiles(self):
        config = Config()
        config.normalization.add_trailing_slash = False
        cfg = config.normalization_for("standard")
        assert cfg.add_trailing_slash is False

    def test_profile_overrides_beat_globals(self):
        config = Config()
        config.normalization.remove_fragment = True  # global
        config.profiles["safe"] = {"remove_fragment": False}
        assert config.normalization_for("safe").remove_fragment is False
        assert config.normalization_for("standard").remove_fragment is True

    def test_preset_defaults(self):
        config = Config()
        safe = config.normalization_for("safe")
        assert safe.remove_fragment is False
        assert safe.sort_query_params is False
        aggressive = config.normalization_for("aggressive")
        assert aggressive.remove_tracking_params is True
        assert aggressive.dedupe_query_params is True


class TestDoNoHarm:
    def test_reserved_encoding_never_decoded(self):
        # %2F in the path must stay encoded: decoding would change semantics.
        assert _n("https://example.com/a%2Fb").normalized == "https://example.com/a%2Fb/"

    def test_ampersand_in_query_value_untouched(self):
        assert (
            _n("https://example.com/p?next=%2Fadmin%3Fx%3D1").normalized
            == "https://example.com/p/?next=%2Fadmin%3Fx%3D1"
        )

    def test_raw_ampersand_in_query_kept(self):
        assert _n("https://example.com/p?a=1&b=2").normalized == "https://example.com/p/?a=1&b=2"
