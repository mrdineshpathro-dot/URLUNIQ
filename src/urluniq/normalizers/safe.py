"""Safe profile: minimal, formatting-noise-only transformations.

The safe normalizer never removes fragments, default ports, dot segments or
query strings; it only lowercases scheme/host and cleans whitespace-level
noise so obviously identical lines collapse.  Query parameter ordering is
always preserved.
"""

from __future__ import annotations

from urluniq.normalizers.base import SafeNormalizer as _SafeNormalizer


class SafeNormalizer(_SafeNormalizer):
    """Minimal transformations: obvious formatting noise only."""


__all__ = ["SafeNormalizer"]
