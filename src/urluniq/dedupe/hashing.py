"""Fast internal URL fingerprints.

URLUNIQ does *not* use hashes as the only URL identity mechanism unless the
user explicitly configures it (``--hash``); by default the full key string is
the identity.  The SQLite backend always stores both the URL and its hash.
"""

from __future__ import annotations

import hashlib

from urluniq.exceptions import ConfigError
from urluniq.models import HashAlgorithm

_HASHERS = {
    HashAlgorithm.SHA256: lambda: hashlib.sha256(),
    HashAlgorithm.SHA1: lambda: hashlib.sha1(),
    HashAlgorithm.MD5: lambda: hashlib.md5(),
}


def fingerprint(value: str, algorithm: HashAlgorithm | str = HashAlgorithm.SHA256) -> str:
    """Return the hex fingerprint of ``value`` using ``algorithm``."""
    algorithm = HashAlgorithm(algorithm)
    if algorithm is HashAlgorithm.XXHASH:
        try:
            import xxhash
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ConfigError(
                "xxhash requested but not installed; run: pip install 'urluniq[performance]'"
            ) from exc
        return xxhash.xxh64_hexdigest(value)
    hasher = _HASHERS[algorithm]()
    hasher.update(value.encode("utf-8", errors="replace"))
    return hasher.hexdigest()
