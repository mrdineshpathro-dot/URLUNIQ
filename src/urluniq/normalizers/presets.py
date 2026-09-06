"""Normalizer presets for the three built-in profiles.

Each preset is a partial :class:`NormalizationConfig` override applied on top
of the dataclass defaults.  Users can extend or override any preset value in
``config/default.toml`` under ``[profiles.<name>]``.
"""

from __future__ import annotations

SAFE_PRESET: dict[str, bool] = {
    "lowercase_scheme": True,
    "lowercase_host": True,
    "idn_to_ascii": False,
    "remove_default_port": False,
    "empty_path_to_slash": False,
    "add_trailing_slash": False,
    "strip_trailing_slash_files": False,
    "collapse_duplicate_slashes": False,
    "remove_dot_segments": False,
    "normalize_percent_encoding": False,
    "encode_non_ascii": True,
    "remove_fragment": False,
    "sort_query_params": False,
    "dedupe_query_params": False,
    "remove_empty_params": False,
    "remove_tracking_params": False,
    "strip_default_index": False,
    "strip_www": False,
    "upgrade_http": False,
    "normalize_ipv4": False,
    "normalize_ipv6": False,
}

STANDARD_PRESET: dict[str, bool] = {
    "lowercase_scheme": True,
    "lowercase_host": True,
    "idn_to_ascii": True,
    "remove_default_port": True,
    "empty_path_to_slash": True,
    "add_trailing_slash": True,
    "strip_trailing_slash_files": True,
    "collapse_duplicate_slashes": True,
    "remove_dot_segments": True,
    "normalize_percent_encoding": True,
    "encode_non_ascii": True,
    "remove_fragment": True,
    "sort_query_params": True,
    "dedupe_query_params": False,
    "remove_empty_params": False,
    "remove_tracking_params": False,
    "strip_default_index": False,
    "strip_www": False,
    "upgrade_http": False,
    "normalize_ipv4": True,
    "normalize_ipv6": True,
}

AGGRESSIVE_PRESET: dict[str, bool] = {
    **STANDARD_PRESET,
    "remove_tracking_params": True,
    "dedupe_query_params": True,
    "strip_default_index": True,
}

PROFILE_PRESETS: dict[str, dict[str, bool]] = {
    "safe": SAFE_PRESET,
    "standard": STANDARD_PRESET,
    "aggressive": AGGRESSIVE_PRESET,
}
