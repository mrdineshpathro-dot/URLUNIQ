"""Normalizer package: profile classes and the builder used by the pipeline."""

from __future__ import annotations

from urluniq.config.loader import Config, NormalizationConfig
from urluniq.models import Profile
from urluniq.normalizers.aggressive import AggressiveNormalizer
from urluniq.normalizers.base import (
    AggressiveNormalizer as BaseAggressive,  # noqa: F401  (re-export)
)
from urluniq.normalizers.base import (
    BaseNormalizer,
    Canonicalizer,
    NormalizeResult,
    collapse_duplicate_slashes,
    normalize_percent_encoding,
    remove_dot_segments,
)
from urluniq.normalizers.base import (
    SafeNormalizer as BaseSafe,  # noqa: F401  (re-export)
)
from urluniq.normalizers.base import (
    StandardNormalizer as BaseStandard,  # noqa: F401  (re-export)
)
from urluniq.normalizers.safe import SafeNormalizer
from urluniq.normalizers.standard import StandardNormalizer

_PROFILE_CLASSES = {
    Profile.SAFE: SafeNormalizer,
    Profile.STANDARD: StandardNormalizer,
    Profile.AGGRESSIVE: AggressiveNormalizer,
}


def build_normalizer(
    profile: Profile | str,
    config: Config,
    redact_userinfo: bool = False,
) -> BaseNormalizer:
    """Create the normalizer for ``profile`` using effective config."""
    profile = Profile(profile)
    norm_cfg = config.normalization_for(profile)
    tracking = config.tracking_params()
    cls = _PROFILE_CLASSES[profile]
    return cls(norm_cfg, config.query, tracking, redact_userinfo=redact_userinfo)


def build_canonicalizer(
    config: Config,
    profile: Profile | str = Profile.STANDARD,
    redact_userinfo: bool = False,
) -> Canonicalizer:
    """Create the canonicalizer (canonical identity form builder)."""
    profile = Profile(profile)
    norm_cfg = config.canonicalization_for()
    tracking = config.tracking_params()
    return Canonicalizer(norm_cfg, config.query, tracking, redact_userinfo=redact_userinfo)


__all__ = [
    "AggressiveNormalizer",
    "BaseAggressive",
    "BaseNormalizer",
    "BaseSafe",
    "BaseStandard",
    "Canonicalizer",
    "NormalizeResult",
    "SafeNormalizer",
    "StandardNormalizer",
    "NormalizationConfig",
    "build_canonicalizer",
    "build_normalizer",
    "collapse_duplicate_slashes",
    "normalize_percent_encoding",
    "remove_dot_segments",
]
