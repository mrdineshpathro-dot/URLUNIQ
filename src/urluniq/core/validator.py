"""Validation stage: reject URLs that are malformed or out of scope.

Validation is syntax-only.  URLUNIQ never resolves DNS and never opens
network connections (see README "Security notes").
"""

from __future__ import annotations

import ipaddress
import re

from urluniq.constants import (
    DEFAULT_ALLOWED_SCHEMES,
    ERR_INVALID_SCHEME,
    ERR_MALFORMED_HOST,
    ERR_MALFORMED_PORT,
    PORT_MAX,
    PORT_MIN,
)
from urluniq.models import ParsedURL

_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_HOST_FULL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$")
_FORBIDDEN_HOST = re.compile(r"[\s<>\"'`\\{}|^%]")


class Validator:
    """Validates parsed URLs against the configured rules."""

    def __init__(
        self,
        allowed_schemes: frozenset[str] | set[str] = DEFAULT_ALLOWED_SCHEMES,
        max_url_length: int = 8192,
    ) -> None:
        self.allowed_schemes = {s.lower() for s in allowed_schemes}
        self.max_url_length = max_url_length

    def validate(self, parsed: ParsedURL) -> str:
        """Return an empty string when valid, otherwise an error reason."""
        if len(parsed.raw) > self.max_url_length:
            return "URL exceeds maximum length"

        if parsed.scheme not in self.allowed_schemes:
            return f"{ERR_INVALID_SCHEME}: '{parsed.scheme or ''}'"

        host = parsed.host
        if not host:
            return ERR_MALFORMED_HOST

        if ":" in host:  # IPv6 literal
            try:
                ipaddress.IPv6Address(host)
            except ValueError:
                return f"{ERR_MALFORMED_HOST}: invalid IPv6 literal"
        elif any(ord(ch) > 127 for ch in host):
            # Internationalized domain: valid when it round-trips through IDNA.
            try:
                host.encode("idna")
            except (UnicodeError, ValueError):
                return f"{ERR_MALFORMED_HOST}: invalid IDN '{host}'"
        else:
            if _FORBIDDEN_HOST.search(host) or ".." in host:
                return f"{ERR_MALFORMED_HOST}: '{host}'"
            if host.endswith("."):
                return f"{ERR_MALFORMED_HOST}: trailing dot"
            # IP-style hosts bypass label rules but must still be addressable text
            if not _is_ip_like(host) and not _HOST_FULL.match(host):
                bad = next(
                    (label for label in host.split(".") if not _HOST_LABEL.match(label)),
                    host,
                )
                return f"{ERR_MALFORMED_HOST}: bad label '{bad}'"

        if parsed.port is not None and not (PORT_MIN <= parsed.port <= PORT_MAX):
            return f"{ERR_MALFORMED_PORT}: {parsed.port}"

        return ""


_IP_LIKE = re.compile(r"^(\d{1,3}\.){0,3}\d{1,3}$|^\d{8,10}$|^0[xX][0-9a-fA-F]+$")


def _is_ip_like(host: str) -> bool:
    """True when the host looks like an IPv4 literal (dotted or alternative)."""
    if not host or not host[0].isdigit():
        return False
    return _IP_LIKE.match(host) is not None
