"""Configuration system.

Loads ``config/default.toml`` (TOML) plus the data files
``tracking_params.txt`` and ``extensions.txt``.  Uses :mod:`tomllib` on
Python >= 3.11 and falls back to a small built-in TOML-subset parser on
3.10, so URLUNIQ stays 100% standard-library.

Resolution order for ``default.toml``:

1. the path passed via ``--config``
2. ``./config/default.toml`` in the current working directory
3. the copy bundled inside the package (``urluniq/data/``)

CLI arguments always override configuration-file settings.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from urluniq.exceptions import ConfigError
from urluniq.models import DedupeMode, HashAlgorithm, Profile

# Built-in fallback tracking list, used only when no tracking_params file is
# found anywhere.  The file is the intended customization point.
BUILTIN_TRACKING_PARAMS: tuple[str, ...] = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "yclid",
    "_ga",
    "msclkid",
    "vero_id",
    "wickedid",
    "twclid",
    "ttclid",
    "li_fat_id",
)

BUILTIN_EXTENSIONS: dict[str, str] = {
    "js": "js",
    "mjs": "js",
    "jsx": "js",
    "map": "static",
    "css": "css",
    "scss": "css",
    "less": "css",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "gif": "image",
    "webp": "image",
    "svg": "image",
    "ico": "image",
    "bmp": "image",
    "avif": "image",
    "pdf": "document",
    "doc": "document",
    "docx": "document",
    "xls": "document",
    "xlsx": "document",
    "ppt": "document",
    "pptx": "document",
    "odt": "document",
    "ods": "document",
    "txt": "document",
    "csv": "document",
    "xml": "document",
    "woff": "static",
    "woff2": "static",
    "ttf": "static",
    "eot": "static",
    "otf": "static",
    "mp4": "static",
    "webm": "static",
    "mp3": "static",
    "wav": "static",
    "zip": "static",
    "rar": "static",
    "gz": "static",
    "tar": "static",
    "7z": "static",
    "swf": "static",
    "html": "html",
    "htm": "html",
    "xhtml": "html",
    "php": "html",
    "asp": "html",
    "aspx": "html",
    "jsp": "html",
    "jspx": "html",
    "cgi": "html",
    "shtml": "html",
    "json": "api",
    "graphql": "api",
}


# ---------------------------------------------------------------------------
# TOML loading (tomllib on 3.11+, mini parser fallback on 3.10)
# ---------------------------------------------------------------------------


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file into a dictionary."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    if sys.version_info >= (3, 11):
        import tomllib

        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    try:
        return _MiniTomlParser(text).parse()
    except ConfigError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


class _MiniTomlParser:
    """Parser for the TOML subset used by URLUNIQ config files.

    Supports comments, ``[dotted.tables]``, basic/literal strings, booleans,
    integers, floats and (multiline) arrays of scalars - deliberately enough
    for ``default.toml`` without third-party dependencies.
    """

    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.n = len(text)

    # -- low-level scanning ------------------------------------------------

    def _peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    def _skip_inline_ws(self) -> None:
        while self._peek() in (" ", "\t"):
            self.i += 1

    def _skip_ws_and_comments(self) -> None:
        while self.i < self.n:
            ch = self._peek()
            if ch in " \t\r\n":
                self.i += 1
            elif ch == "#":
                while self.i < self.n and self.s[self.i] != "\n":
                    self.i += 1
            else:
                break

    def _expect(self, ch: str) -> None:
        if self._peek() != ch:
            raise ConfigError(f"mini-TOML: expected {ch!r} at offset {self.i}")
        self.i += 1

    # -- grammar ------------------------------------------------------------

    def parse(self) -> dict[str, Any]:
        root: dict[str, Any] = {}
        table = root
        while True:
            self._skip_ws_and_comments()
            if self.i >= self.n:
                return root
            if self._peek() == "[":
                table = self._parse_table(root)
            else:
                key, value = self._parse_key_value()
                _set_dotted(table, key, value)

    def _parse_table(self, root: dict[str, Any]) -> dict[str, Any]:
        self._expect("[")
        parts = [self._parse_key_token()]
        while True:
            self._skip_inline_ws()
            if self._peek() == ".":
                self.i += 1
                parts.append(self._parse_key_token())
            elif self._peek() == "]":
                self.i += 1
                break
            else:
                raise ConfigError(f"mini-TOML: bad table header at offset {self.i}")
        table: dict[str, Any] = root
        for part in parts:
            nxt = table.setdefault(part, {})
            if not isinstance(nxt, dict):
                raise ConfigError(f"mini-TOML: table conflict at {'.'.join(parts)}")
            table = nxt
        self._skip_inline_ws()
        if self._peek() == "#":
            self._skip_ws_and_comments()
        return table

    def _parse_key_token(self) -> str:
        self._skip_inline_ws()
        if self._peek() in ('"', "'"):
            return self._parse_string()
        start = self.i
        while self._peek() and (self._peek().isalnum() or self._peek() in "_-"):
            self.i += 1
        if start == self.i:
            raise ConfigError(f"mini-TOML: expected key at offset {self.i}")
        return self.s[start : self.i]

    def _parse_dotted_key(self) -> list[str]:
        parts = [self._parse_key_token()]
        while True:
            self._skip_inline_ws()
            if self._peek() == ".":
                self.i += 1
                parts.append(self._parse_key_token())
            else:
                return parts

    def _parse_key_value(self) -> tuple[list[str], Any]:
        key = self._parse_dotted_key()
        self._skip_inline_ws()
        self._expect("=")
        self._skip_inline_ws()
        value = self._parse_value()
        return key, value

    def _parse_value(self) -> Any:
        ch = self._peek()
        if ch in ('"', "'"):
            return self._parse_string()
        if ch == "[":
            return self._parse_array()
        start = self.i
        while self._peek() and self._peek() not in " \t\r\n#,":
            self.i += 1
        token = self.s[start : self.i]
        if token == "true":
            return True
        if token == "false":
            return False
        for conv in (int, float):
            try:
                return conv(token)
            except ValueError:
                continue
        if token:
            return token
        raise ConfigError(f"mini-TOML: bad value at offset {self.i}")

    def _parse_string(self) -> str:
        quote = self._peek()
        self.i += 1
        if self.s[self.i : self.i + 2] == quote * 2:  # triple-quoted
            self.i += 2
            end = self.s.find(quote * 3, self.i)
            if end == -1:
                raise ConfigError("mini-TOML: unterminated string")
            value = self.s[self.i : end]
            self.i = end + 3
            return value
        out: list[str] = []
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == quote:
                self.i += 1
                return "".join(out)
            if quote == '"' and ch == "\\":
                self.i += 1
                esc = self._peek()
                mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
                if esc in mapping:
                    out.append(mapping[esc])
                    self.i += 1
                elif esc == "u":
                    out.append(chr(int(self.s[self.i + 1 : self.i + 5], 16)))
                    self.i += 5
                else:
                    raise ConfigError(f"mini-TOML: bad escape \\{esc}")
            else:
                out.append(ch)
                self.i += 1
        raise ConfigError("mini-TOML: unterminated string")

    def _parse_array(self) -> list[Any]:
        self._expect("[")
        items: list[Any] = []
        while True:
            self._skip_ws_and_comments()
            if self._peek() == "]":
                self.i += 1
                return items
            items.append(self._parse_value())
            self._skip_ws_and_comments()
            if self._peek() == ",":
                self.i += 1
            elif self._peek() == "]":
                self.i += 1
                return items
            else:
                raise ConfigError(f"mini-TOML: bad array at offset {self.i}")


def _set_dotted(table: dict[str, Any], parts: list[str], value: Any) -> None:
    node = table
    for part in parts[:-1]:
        nxt = node.setdefault(part, {})
        if not isinstance(nxt, dict):
            raise ConfigError(f"mini-TOML: key conflict at {'.'.join(parts)}")
        node = nxt
    node[parts[-1]] = value


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


def _merge_user_normalization(
    base: NormalizationConfig, user: NormalizationConfig
) -> NormalizationConfig:
    """Overlay every non-default field of the user's [normalization] section."""
    defaults = NormalizationConfig()
    overrides = {
        f.name: getattr(user, f.name)
        for f in fields(user)
        if getattr(user, f.name) != getattr(defaults, f.name)
    }
    return replace(base, **overrides)


@dataclass
class NormalizationConfig:
    """Every normalization rule switch.  Profile presets override defaults."""

    lowercase_scheme: bool = True
    lowercase_host: bool = True
    idn_to_ascii: bool = True
    remove_default_port: bool = True
    remove_port: bool = False
    empty_path_to_slash: bool = True
    add_trailing_slash: bool = True
    strip_trailing_slash_files: bool = True
    collapse_duplicate_slashes: bool = True
    remove_dot_segments: bool = True
    normalize_percent_encoding: bool = True
    encode_non_ascii: bool = True
    remove_fragment: bool = True
    sort_query_params: bool = True
    dedupe_query_params: bool = False
    remove_empty_params: bool = False
    remove_tracking_params: bool = False
    strip_default_index: bool = False
    strip_www: bool = False
    upgrade_http: bool = False
    normalize_ipv4: bool = True
    normalize_ipv6: bool = True

    def merged(self, overrides: dict[str, Any]) -> NormalizationConfig:
        """Return a copy with boolean/known-field overrides applied."""
        valid = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in valid}
        return replace(self, **clean)


@dataclass
class QueryConfig:
    """Smart query-parameter engine settings."""

    case_sensitive_names: bool = False
    duplicate_keep: str = "first"  # "first" | "last"
    keep_params: list[str] = field(default_factory=list)
    drop_params: list[str] = field(default_factory=list)
    tracking_params: list[str] = field(default_factory=list)  # extra entries
    tracking_params_file: str = "tracking_params.txt"


@dataclass
class DedupeConfig:
    mode: DedupeMode = DedupeMode.NORMALIZED
    hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256
    use_hash_keys: bool = False  # only fingerprint when explicitly configured
    smart_ignore_tracking: bool = True
    smart_ignore_session: bool = True
    smart_ignore_empty: bool = True


@dataclass
class ClassificationConfig:
    enabled: bool = False
    extensions_file: str = "extensions.txt"


@dataclass
class FiltersConfig:
    include_host: list[str] = field(default_factory=list)
    exclude_host: list[str] = field(default_factory=list)
    include_extension: list[str] = field(default_factory=list)
    exclude_extension: list[str] = field(default_factory=list)
    include_path: list[str] = field(default_factory=list)
    exclude_path: list[str] = field(default_factory=list)
    include_regex: list[str] = field(default_factory=list)
    exclude_regex: list[str] = field(default_factory=list)
    domain: str = ""
    include_subdomains: bool = False


@dataclass
class OutputConfig:
    format: str = "txt"
    sort: str = "none"  # none | url | host | category
    top_n: int = 10
    csv_header: bool = True
    duplicates_max_groups: int = 1000
    duplicates_max_variants: int = 50


@dataclass
class PerformanceConfig:
    workers: int = 1
    backend: str = "memory"
    sqlite_path: str = "urluniq.db"
    resume: bool = False
    chunk_size: int = 20_000
    progress_interval: int = 100_000
    multiprocess_min_lines: int = 200_000
    process_cache_size: int = 200_000


@dataclass
class LoggingConfig:
    file: str = ""
    format: str = "text"  # text | json
    level: str = "INFO"


@dataclass
class ValidationConfig:
    allowed_schemes: list[str] = field(
        default_factory=lambda: ["http", "https", "ftp", "ftps", "ws", "wss"]
    )
    max_url_length: int = 8192


@dataclass
class PluginsConfig:
    enabled: bool = True
    example_tracking: bool = False
    example_classifier: bool = False


@dataclass
class Config:
    """Effective configuration for one URLUNIQ run."""

    config_path: Path | None = None
    profile: Profile = Profile.STANDARD
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    canonicalization: dict[str, Any] = field(default_factory=dict)

    # runtime caches -----------------------------------------------------
    _extra_tracking: set[str] = field(default_factory=set, repr=False)
    _extension_map: dict[str, str] | None = field(default=None, repr=False)

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Load configuration from ``path`` or the standard locations."""
        data: dict[str, Any] = {}
        config_path: Path | None = None
        candidate = Path(path) if path else None
        if candidate is not None:
            if not candidate.is_file():
                raise ConfigError(f"config file not found: {candidate}")
            config_path = candidate
            data = load_toml(candidate)
        else:
            for location in default_config_locations():
                if location.is_file():
                    config_path = location
                    data = load_toml(location)
                    break
        cfg = cls.from_dict(data)
        cfg.config_path = config_path
        return cfg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Build a Config from a parsed TOML dictionary."""
        cfg = cls()
        _apply_section(cfg.normalization, data.get("normalization", {}))
        _apply_section(cfg.query, data.get("query", {}))
        _apply_section(cfg.output, data.get("output", {}))
        _apply_section(cfg.performance, data.get("performance", {}))
        _apply_section(cfg.logging, data.get("logging", {}))
        _apply_section(cfg.filters, data.get("filters", {}))
        _apply_section(cfg.plugins, data.get("plugins", {}))
        _apply_section(cfg.classification, data.get("classification", {}))

        validation = data.get("validation", {})
        _apply_section(cfg.validation, validation)

        dedupe = data.get("dedupe", {})
        _apply_section(cfg.dedupe, dedupe)

        raw_mode = dedupe.get("mode")
        if raw_mode:
            try:
                cfg.dedupe.mode = DedupeMode(str(raw_mode).lower())
            except ValueError as exc:
                raise ConfigError(f"unknown dedupe mode: {raw_mode}") from exc
        raw_hash = dedupe.get("hash_algorithm")
        if raw_hash:
            try:
                cfg.dedupe.hash_algorithm = HashAlgorithm(str(raw_hash).lower())
            except ValueError as exc:
                raise ConfigError(f"unknown hash algorithm: {raw_hash}") from exc

        raw_profile = data.get("profile")
        if raw_profile:
            try:
                cfg.profile = Profile(str(raw_profile).lower())
            except ValueError as exc:
                raise ConfigError(f"unknown profile: {raw_profile}") from exc

        profiles = data.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ConfigError("[profiles] must be a table")
        cfg.profiles = profiles
        cfg.canonicalization = data.get("canonicalization", {})
        return cfg

    # -- derived settings ----------------------------------------------------

    def normalization_for(self, profile: Profile | str) -> NormalizationConfig:
        """Effective normalization config for a profile (presets + overrides).

        Overlay order: dataclass defaults -> built-in profile preset ->
        user ``[normalization]`` globals -> user ``[profiles.<name>]``.
        """
        from urluniq.normalizers.presets import PROFILE_PRESETS

        profile = Profile(profile)
        cfg = NormalizationConfig().merged(PROFILE_PRESETS.get(profile.value, {}))
        cfg = _merge_user_normalization(cfg, self.normalization)
        profile_overrides = self.profiles.get(profile.value, {})
        if not isinstance(profile_overrides, dict):
            raise ConfigError(f"[profiles.{profile.value}] must be a table")
        return cfg.merged(profile_overrides)

    def canonicalization_for(self) -> NormalizationConfig:
        """Canonicalizer settings ([canonicalization] overrides defaults).

        Canonical defaults are stronger than *standard* so URLs identifying
        the same resource converge: fragments removed, query sorted and
        de-duplicated, tracking parameters dropped, index documents dropped.
        """
        from urluniq.normalizers.presets import STANDARD_PRESET

        canonical_defaults = {
            **STANDARD_PRESET,
            "remove_tracking_params": True,
            "strip_default_index": True,
            "dedupe_query_params": True,
            "upgrade_http": True,  # canonical identity merges http/https (spec 12)
            "remove_empty_params": False,
        }
        cfg = NormalizationConfig().merged(canonical_defaults)
        return cfg.merged(self.canonicalization)

    def tracking_params(self) -> set[str]:
        """Full tracking-parameter set (builtin + file + config + plugins)."""
        names: set[str] = set(BUILTIN_TRACKING_PARAMS)
        path = self.resolve_data_file(self.query.tracking_params_file)
        if path is not None:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    entry = line.split("#", 1)[0].strip()
                    if entry:
                        names.add(entry)
            except OSError:
                pass
        names.update(p.lower() for p in self.query.tracking_params)
        names.update(self._extra_tracking)
        return names

    def add_tracking_params(self, names: set[str] | list[str]) -> None:
        """Register additional tracking parameters (used by plugins)."""
        self._extra_tracking.update(n.lower() for n in names)

    def extension_map(self) -> dict[str, str]:
        """Extension -> category mapping from extensions.txt (cached)."""
        if self._extension_map is not None:
            return self._extension_map
        mapping: dict[str, str] = dict(BUILTIN_EXTENSIONS)
        path = self.resolve_data_file(self.classification.extensions_file)
        if path is not None:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    entry = line.split("#", 1)[0].strip()
                    if not entry or ":" not in entry:
                        continue
                    category, _, exts = entry.partition(":")
                    for ext in exts.split(","):
                        ext = ext.strip().lower().lstrip(".")
                        if ext:
                            mapping[ext] = category.strip().lower()
            except OSError:
                pass
        self._extension_map = mapping
        return mapping

    def resolve_data_file(self, name: str) -> Path | None:
        """Locate a data file near the config, in ./config, or in the package."""
        candidates: list[Path] = []
        if self.config_path is not None:
            candidates.append(self.config_path.parent / name)
        candidates.append(Path.cwd() / "config" / name)
        candidates.append(Path.cwd() / name)
        package_dir = Path(__file__).resolve().parent.parent / "data"
        candidates.append(package_dir / name)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializable view of the effective configuration."""
        return {
            "config_path": str(self.config_path) if self.config_path else None,
            "profile": self.profile.value,
            "normalization": asdict(self.normalization),
            "query": asdict(self.query),
            "dedupe": {
                **asdict(self.dedupe),
                "mode": self.dedupe.mode.value,
                "hash_algorithm": self.dedupe.hash_algorithm.value,
            },
            "classification": asdict(self.classification),
            "filters": asdict(self.filters),
            "output": asdict(self.output),
            "performance": asdict(self.performance),
            "logging": asdict(self.logging),
            "validation": asdict(self.validation),
            "plugins": asdict(self.plugins),
            "profiles": self.profiles,
            "canonicalization": self.canonicalization,
        }


def _apply_section(target: Any, section: dict[str, Any]) -> None:
    """Copy known keys from a TOML section onto a config dataclass."""
    for f in fields(target):
        if f.name in section:
            value = section[f.name]
            current = getattr(target, f.name)
            if isinstance(current, bool) and not isinstance(value, bool):
                raise ConfigError(f"config key '{f.name}' must be a boolean")
            if isinstance(current, list):
                if isinstance(value, list):
                    setattr(target, f.name, [str(v) for v in value])
                else:
                    setattr(target, f.name, [str(value)])
            else:
                setattr(target, f.name, value)


def default_config_locations() -> list[Path]:
    """Search order for default.toml when --config is not given."""
    return [
        Path.cwd() / "config" / "default.toml",
        Path.cwd() / "default.toml",
        Path(__file__).resolve().parent.parent / "data" / "default.toml",
    ]
