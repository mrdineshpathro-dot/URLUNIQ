"""Normalization engine foundation.

Implements the rule-driven :class:`BaseNormalizer` used by the safe /
standard / aggressive profiles, plus the :class:`Canonicalizer` that builds
the canonical form used for canonical deduplication.

Every transformation records a human-readable reason so ``--explain``,
duplicate reports and HTML reports can always answer *why* a URL changed.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlunsplit

from urluniq.config.loader import NormalizationConfig, QueryConfig
from urluniq.constants import (
    DEFAULT_INDEX_FILES,
    DEFAULT_PORTS,
    PATH_SAFE_RAW,
    REASON_DEFAULT_PORT_REMOVED,
    REASON_DOT_SEGMENTS,
    REASON_DUP_SLASHES,
    REASON_EMPTY_PATH,
    REASON_FRAGMENT_REMOVED,
    REASON_HOST_LOWERED,
    REASON_IDN_ENCODED,
    REASON_INDEX_STRIPPED,
    REASON_IPV4_NORMALIZED,
    REASON_IPV6_NORMALIZED,
    REASON_PERCENT_NORMALIZED,
    REASON_PORT_NORMALIZED,
    REASON_SCHEME_LOWERED,
    REASON_SCHEME_UPGRADED,
    REASON_TRAILING_SLASH_ADDED,
    REASON_TRAILING_SLASH_REMOVED,
    REASON_USERINFO_REDACTED,
    REASON_WWW_STRIPPED,
    UNRESERVED_CHARS,
)
from urluniq.core.parser import normalize_ipv4_literal, path_extension
from urluniq.models import ParsedURL
from urluniq.normalizers.query import QueryEngine


@dataclass(slots=True)
class NormalizeResult:
    """Outcome of normalizing one URL."""

    url: str
    reasons: list[str] = field(default_factory=list)
    tracking_removed: int = 0
    param_names: list[str] = field(default_factory=list)
    scheme: str = ""
    host: str = ""
    port: int | None = None
    path: str = ""
    query: str = ""


def normalize_percent_encoding(
    component: str,
    safe_raw: frozenset[str] | set[str],
    encode_non_ascii: bool = True,
) -> str:
    """Normalize percent-encoding inside a single URL component.

    * ``%2f`` / ``%2F`` style triplets are re-emitted with uppercase hex;
    * percent-encoded *unreserved* characters are decoded (``%7E`` -> ``~``);
    * characters that may not appear raw (spaces, control chars, non-ASCII)
      are percent-encoded as UTF-8;
    * everything else is preserved exactly - reserved characters encoded by
      the origin server stay encoded, so resource semantics never change.
    """
    # Fast path: a printable-ASCII component without any '%' whose characters
    # are all raw-safe needs no work at all (most real-world URLs).
    if "%" not in component and component.isascii() and _is_printable_ascii(component):
        pattern = _raw_ok_pattern(safe_raw)
        if pattern.fullmatch(component):
            return component
    out: list[str] = []
    i = 0
    length = len(component)
    while i < length:
        ch = component[i]
        if ch == "%":
            hex_part = component[i + 1 : i + 3]
            if len(hex_part) == 2 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                code = int(hex_part, 16)
                decoded = chr(code)
                if decoded in UNRESERVED_CHARS:
                    out.append(decoded)
                else:
                    out.append(f"%{code:02X}")
                i += 3
                continue
            # A literal '%' that is not part of a triplet: encode it.
            out.append("%25")
            i += 1
            continue
        if ch in safe_raw:
            out.append(ch)
        else:
            encoded = quote(ch, encoding="utf-8", safe="")
            out.append(encoded if (encode_non_ascii or ord(ch) < 128) else ch)
        i += 1
    return "".join(out)


_NON_PRINTABLE = re.compile(r"[^\x21-\x7e]")
_RAW_OK_CACHE: dict[frozenset[str], re.Pattern[str]] = {}


def _is_printable_ascii(component: str) -> bool:
    return _NON_PRINTABLE.search(component) is None


def _raw_ok_pattern(safe_raw: frozenset[str] | set[str]) -> re.Pattern[str]:
    key = frozenset(safe_raw)
    pattern = _RAW_OK_CACHE.get(key)
    if pattern is None:
        chars = "".join(re.escape(c) for c in sorted(key))
        pattern = re.compile(f"[{chars}]*")
        _RAW_OK_CACHE[key] = pattern
    return pattern


def remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4 remove_dot_segments."""
    if "." not in path:
        return path
    output: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if output and output[-1] != "..":
                output.pop()
            continue
        output.append(segment)
    rebuilt = "/".join(output)
    if path.endswith("/.") or path.endswith("/.."):
        rebuilt += "/"
    if not rebuilt.startswith("/") and path.startswith("/"):
        rebuilt = "/" + rebuilt
    return rebuilt


def collapse_duplicate_slashes(path: str) -> str:
    """Collapse '//' runs in a path to a single '/'."""
    if "//" not in path:
        return path
    parts = [p for p in path.split("/") if p != ""]
    rebuilt = "/" + "/".join(parts)
    return rebuilt + "/" if path.endswith("/") else rebuilt


def _bracket_host(host: str) -> str:
    return f"[{host}]" if ":" in host else host


class BaseNormalizer:
    """Rule-driven normalizer; behaviour is fully controlled by config."""

    def __init__(
        self,
        norm_config: NormalizationConfig,
        query_config: QueryConfig,
        tracking_params: set[str] | None = None,
        redact_userinfo: bool = False,
    ) -> None:
        self.cfg = norm_config
        self.queries = QueryEngine(query_config, tracking_params or set())
        self.redact = redact_userinfo

    # -- helpers ---------------------------------------------------------

    def _normalize_scheme(self, parsed: ParsedURL, reasons: list[str]) -> str:
        scheme = parsed.scheme
        if self.cfg.lowercase_scheme and scheme != scheme.lower():
            reasons.append(REASON_SCHEME_LOWERED)
        scheme = scheme.lower()
        if self.cfg.upgrade_http and scheme == "http":
            scheme = "https"
            reasons.append(REASON_SCHEME_UPGRADED)
        return scheme

    def _normalize_host(self, parsed: ParsedURL, reasons: list[str]) -> str:
        host = parsed.host
        raw_host = parsed.host_raw or host
        if self.cfg.lowercase_host and raw_host != raw_host.lower():
            reasons.append(REASON_HOST_LOWERED)
        host = host.lower()
        if self.cfg.idn_to_ascii and not host.isascii():
            try:
                host = host.encode("idna").decode("ascii")
                reasons.append(REASON_IDN_ENCODED)
            except (UnicodeError, ValueError):
                pass  # keep the unicode host rather than failing
        if self.cfg.normalize_ipv4 and ":" not in host:
            expanded = normalize_ipv4_literal(host)
            if expanded != host:
                host = expanded
                reasons.append(REASON_IPV4_NORMALIZED)
        if self.cfg.normalize_ipv6 and ":" in host:
            try:
                compressed = str(ipaddress.IPv6Address(host))
            except ValueError:
                compressed = host
            if compressed != host:
                host = compressed
                reasons.append(REASON_IPV6_NORMALIZED)
        if self.cfg.strip_www and host.startswith("www."):
            host = host[4:]
            reasons.append(REASON_WWW_STRIPPED)
        return host

    def _normalize_port(self, parsed: ParsedURL, reasons: list[str]) -> int | None:
        if parsed.port is None:
            return None
        if self.cfg.remove_default_port and DEFAULT_PORTS.get(parsed.scheme) == parsed.port:
            reasons.append(REASON_DEFAULT_PORT_REMOVED)
            return None
        if self.cfg.remove_port:
            reasons.append(REASON_PORT_NORMALIZED)
            return None
        return parsed.port

    def _normalize_path(self, parsed: ParsedURL, reasons: list[str]) -> str:
        path = parsed.path
        if self.cfg.normalize_percent_encoding:
            encoded = normalize_percent_encoding(
                path, PATH_SAFE_RAW, encode_non_ascii=self.cfg.encode_non_ascii
            )
            if encoded != path:
                reasons.append(REASON_PERCENT_NORMALIZED)
            path = encoded
        if self.cfg.collapse_duplicate_slashes and "//" in path:
            path = collapse_duplicate_slashes(path)
            reasons.append(REASON_DUP_SLASHES)
        if self.cfg.remove_dot_segments and path not in ("", "/"):
            reduced = remove_dot_segments(path)
            if reduced != path:
                path = reduced
                reasons.append(REASON_DOT_SEGMENTS)
        if path == "" and self.cfg.empty_path_to_slash:
            path = "/"
            reasons.append(REASON_EMPTY_PATH)
        if self.cfg.strip_default_index:
            last = path.rstrip("/").rsplit("/", 1)[-1].lower()
            if last in DEFAULT_INDEX_FILES:
                path = path.rstrip("/")[: -len(last)] or "/"
                reasons.append(REASON_INDEX_STRIPPED)
        if (
            self.cfg.add_trailing_slash
            and path
            and not path.endswith("/")
            and not path_extension(path)
        ):
            path += "/"
            reasons.append(REASON_TRAILING_SLASH_ADDED)
        if self.cfg.strip_trailing_slash_files and path.endswith("/") and len(path) > 1:
            stem = path.rstrip("/")
            if path_extension(stem):
                path = stem
                reasons.append(REASON_TRAILING_SLASH_REMOVED)
        return path

    def _normalize_userinfo(self, parsed: ParsedURL, reasons: list[str]) -> str:
        if not parsed.has_userinfo:
            return ""
        if self.redact:
            reasons.append(REASON_USERINFO_REDACTED)
            return "[REDACTED]@"
        user = parsed.username or ""
        if parsed.password is not None:
            return f"{user}:{parsed.password}@"
        return f"{user}@"

    # -- main entry -------------------------------------------------------

    def apply(self, parsed: ParsedURL) -> NormalizeResult:
        """Normalize one parsed URL and rebuild the URL string."""
        reasons: list[str] = []
        scheme = self._normalize_scheme(parsed, reasons)
        host = self._normalize_host(parsed, reasons)
        port = self._normalize_port(parsed, reasons)
        path = self._normalize_path(parsed, reasons)

        query_result = self.queries.process(parsed.query, self.cfg)
        reasons.extend(query_result.reasons)

        fragment = "" if self.cfg.remove_fragment else parsed.fragment
        if not fragment and parsed.fragment:
            reasons.append(REASON_FRAGMENT_REMOVED)

        netloc = f"{self._normalize_userinfo(parsed, reasons)}{_bracket_host(host)}"
        if port is not None:
            netloc += f":{port}"

        url = urlunsplit((scheme, netloc, path, query_result.query, fragment))
        return NormalizeResult(
            url=url,
            reasons=reasons,
            tracking_removed=query_result.tracking_removed,
            param_names=query_result.param_names,
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            query=query_result.query,
        )


class SafeNormalizer(BaseNormalizer):
    """Minimal transformations: obvious formatting noise only."""


class StandardNormalizer(BaseNormalizer):
    """Defaults: semantics-preserving normalization for clean datasets."""


class AggressiveNormalizer(BaseNormalizer):
    """Additional canonicalization; may merge URLs that are merely similar."""


class Canonicalizer(BaseNormalizer):
    """Builds the canonical identity used by canonical/smart deduplication.

    Expects a :class:`NormalizationConfig` already merged via
    ``Config.canonicalization_for()`` (fragments removed, query sorted and
    de-duplicated, tracking parameters dropped by default) so that URLs
    identifying the same resource converge.
    """
