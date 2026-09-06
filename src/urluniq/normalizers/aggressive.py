"""Aggressive profile: additional canonicalization.

Everything in *standard*, plus:

* tracking-parameter removal (configurable list)
* duplicate query-parameter removal
* default index documents (``index.html`` ...) collapsed to the directory
* optionally stripping ``www.`` or upgrading http -> https (off by default,
  enable through ``config/default.toml``)

Aggressive mode may merge URLs that are merely *similar*; use it when you
care about endpoint inventory rather than exact resources.
"""

from __future__ import annotations

from urluniq.normalizers.base import AggressiveNormalizer as _AggressiveNormalizer


class AggressiveNormalizer(_AggressiveNormalizer):
    """Additional canonicalization; may merge URLs that are merely similar."""


__all__ = ["AggressiveNormalizer"]
