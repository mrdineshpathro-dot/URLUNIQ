"""Configuration package (loader); data files live in ``urluniq/data``."""

from urluniq.config.loader import (
    Config,
    NormalizationConfig,
    QueryConfig,
    load_toml,
)

__all__ = ["Config", "NormalizationConfig", "QueryConfig", "load_toml"]
