"""URL parsing, component helpers and feature extraction.

The parser wraps :func:`urllib.parse.urlsplit` with defensive handling for
untrusted input (control characters, whitespace, bracketed IPv6 hosts, IDN
hosts and alternative IPv4 notations).
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from urluniq.constants import SECOND_LEVEL_SUFFIXES
from urluniq.exceptions import URLValidationError
from urluniq.models import Features, ParsedURL, URLRecord

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_IPV4_ALT = re.compile(r"^\d{1,3}(?:\.\d{1,3}){0,2}$|^\d{8,10}$|^0[xX][0-9a-fA-F]+$")

DEFAULT_MAX_URL_LENGTH = 8192


def _clean_raw(raw: str, max_length: int = DEFAULT_MAX_URL_LENGTH) -> tuple[str, list[str]]:
    """Trim whitespace/control noise from a raw input line.

    Returns the cleaned string plus a list of applied cleanup reasons.
    """
    reasons: list[str] = []
    cleaned = raw.strip()
    if cleaned != raw:
        reasons.append("surrounding whitespace removed")
    no_ctl = _CONTROL_CHARS.sub("", cleaned)
    if no_ctl != cleaned:
        reasons.append("control characters removed")
    if len(no_ctl) > max_length:
        raise URLValidationError("URL exceeds maximum length")
    return no_ctl, reasons


def parse_url(
    raw: str,
    max_length: int = DEFAULT_MAX_URL_LENGTH,
) -> tuple[ParsedURL | None, str, list[str]]:
    """Parse a raw URL string.

    Returns ``(parsed, error_reason, cleanup_reasons)``.  ``parsed`` is
    ``None`` when the URL cannot be parsed; ``error_reason`` is empty on
    success.  ``cleanup_reasons`` describe formatting noise removed from the
    raw input (whitespace / control characters).
    """
    from urluniq.constants import ERR_EMPTY_URL, ERR_INVALID_STRUCTURE, ERR_MALFORMED_PORT

    try:
        cleaned, reasons = _clean_raw(raw, max_length)
    except URLValidationError:
        return None, "URL exceeds maximum length", []

    if not cleaned:
        return None, ERR_EMPTY_URL, []

    try:
        parts = urlsplit(cleaned)
    except ValueError as exc:
        message = str(exc)
        if "port" in message.lower() or "out of range" in message.lower():
            return None, f"{ERR_MALFORMED_PORT}: {message}", reasons
        return None, f"{ERR_INVALID_STRUCTURE}: {exc}", reasons

    if parts.scheme == "" or parts.netloc == "":
        # urlsplit accepts "example.com/path" but treats it as path-only.
        return None, ERR_INVALID_STRUCTURE, reasons

    try:
        port = parts.port
    except ValueError as exc:
        return None, f"{ERR_MALFORMED_PORT}: {exc}", reasons

    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    # Recover the original-case host from the netloc for change reporting
    # (urlsplit's .hostname is always lowercased).
    host_part = parts.netloc.rsplit("@", 1)[-1]
    if host_part.startswith("["):
        host_raw = host_part.split("]", 1)[0] + "]"
    else:
        host_raw = host_part.split(":", 1)[0]
    if host_raw.startswith("[") and host_raw.endswith("]"):
        host_raw = host_raw[1:-1]
    # urlsplit un-brackets IPv6 hosts; keep the bare form.
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    parsed = ParsedURL(
        raw=cleaned,
        scheme=scheme,
        username=parts.username,
        password=parts.password,
        host=host,
        host_raw=host_raw,
        port=port,
        path=parts.path,
        query=parts.query,
        fragment=parts.fragment,
        explicit_port=":" in parts.netloc.rsplit("@", 1)[-1],
        is_ipv6=":" in host,
        is_ipv4=bool(_IPV4_ALT.match(host or "")) and ":" not in (host or ""),
        is_idn=not host.isascii(),
    )
    return parsed, "", reasons


def normalize_ipv4_literal(host: str) -> str:
    """Expand alternative IPv4 notations to dotted quad.

    ``2130706433`` -> ``127.0.0.1``, ``0x7f000001`` -> ``127.0.0.1``,
    ``127.1`` -> ``127.0.0.1`` (classic inet_aton semantics).  Returns the
    input unchanged when it is already a dotted quad or not an IPv4 literal.
    """
    if not host or ":" in host or not _IPV4_ALT.match(host):
        return host
    try:
        ipaddress.IPv4Address(host)
        return host
    except ValueError:
        pass

    def _int(token: str) -> int | None:
        try:
            return int(token, 16) if token[:2].lower() == "0x" else int(token, 10)
        except ValueError:
            return None

    parts = host.split(".")
    nums: list[int | None] = [_int(p) for p in parts]
    if len(parts) == 1:
        value = nums[0]
        if value is not None and 0 <= value <= 0xFFFFFFFF:
            return str(ipaddress.IPv4Address(value))
        return host
    if len(parts) == 4:
        if all(n is not None and 0 <= n <= 255 for n in nums):
            return ".".join(str(n) for n in nums if n is not None)
        return host
    if len(parts) in (2, 3):
        if any(n is None for n in nums):
            return host
        values = [n for n in nums if n is not None]
        head, tail = values[:-1], values[-1]
        if any(not 0 <= n <= 255 for n in head):
            return host
        tail_bits = (5 - len(parts)) * 8
        if not 0 <= tail < (1 << tail_bits):
            return host
        value = 0
        for i, n in enumerate(head):
            value |= n << (24 - 8 * i)
        value |= tail
        return str(ipaddress.IPv4Address(value))
    return host


def is_ipv6_literal(host: str) -> bool:
    """Return True when ``host`` is an IPv6 literal."""
    try:
        ipaddress.IPv6Address(host)
    except ValueError:
        return False
    return True


def path_extension(path: str) -> str:
    """Return the lowercased file extension of the final path segment.

    Leading-dot files (``.well-known``) and extensionless segments return "".
    """
    segment = path.rsplit("/", 1)[-1]
    if not segment or segment.startswith("."):
        dot = segment.find(".", 1)
        if dot == -1:
            return ""
        return segment[dot + 1 :].lower()
    if "." not in segment:
        return ""
    return segment.rsplit(".", 1)[-1].lower()


def path_depth(path: str) -> int:
    """Number of meaningful segments in a path ('/' -> 0)."""
    if path in ("", "/"):
        return 0
    return len([seg for seg in path.split("/") if seg not in ("", ".")])


def split_path(path: str) -> tuple[str, str]:
    """Split a path into ``(directory, filename)``.

    ``/a/b/c.js`` -> ``('/a/b/', 'c.js')``; ``/a/b/`` -> ``('/a/b/', '')``.
    """
    if "/" not in path.rstrip("/"):
        return ("/", path.rstrip("/")) if path.rstrip("/") else ("/", "")
    directory, _, filename = path.rpartition("/")
    return f"{directory}/", filename


def registrable_domain(host: str) -> str:
    """Heuristic registrable domain (eTLD+1) without a full Public Suffix List.

    Handles common second-level suffixes (co.uk, com.au, ...).  IP literals
    and single-label hosts are returned unchanged.
    """
    if not host or ":" in host:
        return host
    if host[0].isdigit():
        try:
            ipaddress.IPv4Address(host)
            return host
        except ValueError:
            pass
    labels = host.split(".")
    if len(labels) < 2:
        return host
    if len(labels) >= 3 and ".".join(labels[-2:]).lower() in SECOND_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def subdomain_of(host: str) -> str:
    """Subdomain part of ``host`` relative to its registrable domain."""
    domain = registrable_domain(host)
    if not domain or host == domain:
        return ""
    return host[: -(len(domain) + 1)]


def build_features(record: URLRecord, parsed: ParsedURL) -> Features:
    """Assemble the full feature set for a processed URL record."""
    directory, filename = split_path(record.path or parsed.path)
    port = parsed.effective_port
    return Features(
        url=record.raw,
        normalized_url=record.normalized,
        canonical_url=record.canonical,
        scheme=record.scheme,
        host=record.host,
        subdomain=record.subdomain,
        registrable_domain=record.registrable_domain,
        port=port,
        path=record.path or parsed.path,
        directory=directory,
        filename=filename,
        extension=record.extension,
        query_param_count=record.param_count,
        query_param_names=list(record.param_names),
        has_fragment=record.has_fragment,
        url_length=record.url_length,
        path_depth=record.path_depth,
        category=record.category,
    )
