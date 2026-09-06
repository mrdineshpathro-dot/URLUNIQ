"""Standard profile (default): semantics-preserving normalization.

* scheme and hostname normalized (including IDN/punycode, IPv4/IPv6 forms)
* default ports removed
* empty paths expanded to ``/`` and trailing slashes made consistent
* duplicate slashes and dot segments resolved
* safe percent-encoding normalization
* fragments removed
* query parameters sorted; duplicates preserved
"""

from __future__ import annotations

from urluniq.normalizers.base import StandardNormalizer as _StandardNormalizer


class StandardNormalizer(_StandardNormalizer):
    """Defaults: semantics-preserving normalization for clean datasets."""


__all__ = ["StandardNormalizer"]
