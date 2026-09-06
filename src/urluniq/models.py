"""Core data models: parsed URLs, processing records, features and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Profile(str, Enum):
    """Normalization profile presets."""

    SAFE = "safe"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class DedupeMode(str, Enum):
    """Deduplication strategies."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    CANONICAL = "canonical"
    HOST = "host"
    PATH = "path"
    PATH_QUERY = "path_query"
    SMART = "smart"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class OutputFormat(str, Enum):
    """Supported output formats."""

    TXT = "txt"
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class HashAlgorithm(str, Enum):
    """Fingerprint algorithms for the deduplication engine."""

    SHA256 = "sha256"
    SHA1 = "sha1"
    MD5 = "md5"
    XXHASH = "xxhash"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Backend(str, Enum):
    """Deduplication storage backends."""

    MEMORY = "memory"
    SQLITE = "sqlite"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(slots=True)
class ParsedURL:
    """A URL split into components by :mod:`urluniq.core.parser`.

    Attributes mirror the RFC 3986 components.  ``port`` is ``None`` when the
    URL carries no explicit port.  IPv6 hosts are stored *without* brackets.
    """

    raw: str
    scheme: str = ""
    username: str | None = None
    password: str | None = None
    host: str = ""
    host_raw: str = ""
    port: int | None = None
    path: str = ""
    query: str = ""
    fragment: str = ""
    explicit_port: bool = False
    is_ipv6: bool = False
    is_ipv4: bool = False
    is_idn: bool = False

    @property
    def has_userinfo(self) -> bool:
        return self.username is not None or self.password is not None

    @property
    def effective_port(self) -> int:
        from urluniq.constants import DEFAULT_PORTS

        if self.port is not None:
            return self.port
        return DEFAULT_PORTS.get(self.scheme, 80)

    def query_pairs(self) -> list[list[str]]:
        """Return raw query pairs (``[name, value]``) without decoding."""
        if not self.query:
            return []
        return [pair.split("=", 1) if "=" in pair else [pair] for pair in self.query.split("&")]


@dataclass(slots=True)
class URLRecord:
    """Everything URLUNIQ knows about one input URL while processing."""

    raw: str
    normalized: str = ""
    canonical: str = ""
    category: str = ""
    reasons: list[str] = field(default_factory=list)
    tracking_removed: int = 0
    error: str = ""
    dropped: bool = False
    drop_reason: str = ""
    # Component snapshots used by dedupe keys, filters and statistics.
    scheme: str = ""
    host: str = ""
    port: int = 0
    path: str = ""
    query: str = ""
    extension: str = ""
    param_count: int = 0
    param_names: list[str] = field(default_factory=list)
    has_fragment: bool = False
    has_userinfo: bool = False
    url_length: int = 0
    path_depth: int = 0
    registrable_domain: str = ""
    subdomain: str = ""
    features: dict[str, Any] | None = None

    @property
    def valid(self) -> bool:
        return not self.error


@dataclass(slots=True)
class Features:
    """Extractable per-URL features (see ``--extract-features``)."""

    url: str
    normalized_url: str
    canonical_url: str
    scheme: str
    host: str
    subdomain: str
    registrable_domain: str
    port: int
    path: str
    directory: str
    filename: str
    extension: str
    query_param_count: int
    query_param_names: list[str]
    has_fragment: bool
    url_length: int
    path_depth: int
    category: str

    def to_dict(self) -> dict[str, Any]:
        """Return the feature set as an ordered dictionary."""
        return {
            "url": self.url,
            "normalized_url": self.normalized_url,
            "canonical_url": self.canonical_url,
            "scheme": self.scheme,
            "host": self.host,
            "subdomain": self.subdomain,
            "registrable_domain": self.registrable_domain,
            "port": self.port,
            "path": self.path,
            "directory": self.directory,
            "filename": self.filename,
            "extension": self.extension,
            "query_param_count": self.query_param_count,
            "query_param_names": self.query_param_names,
            "has_fragment": self.has_fragment,
            "url_length": self.url_length,
            "path_depth": self.path_depth,
            "category": self.category,
        }


@dataclass(slots=True)
class URLResult:
    """Return type of the public :func:`urluniq.normalize_url` API.

    Subscript-free convenience: ``str(result)`` and ``print(result)`` yield the
    normalized URL so the object behaves like a string in scripts.
    """

    original: str
    normalized: str = ""
    canonical: str = ""
    category: str = ""
    changes: list[str] = field(default_factory=list)
    error: str = ""

    def __str__(self) -> str:
        return self.normalized

    def __bool__(self) -> bool:
        return not self.error

    @property
    def is_valid(self) -> bool:
        return not self.error
