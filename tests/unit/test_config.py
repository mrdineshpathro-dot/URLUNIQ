"""Unit tests for the configuration system, including the mini TOML parser."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from urluniq.config.loader import Config, _MiniTomlParser, load_toml
from urluniq.exceptions import ConfigError
from urluniq.models import DedupeMode, HashAlgorithm, Profile

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOML = REPO_ROOT / "config" / "default.toml"


class TestMiniTomlParser:
    def parse(self, text: str):
        return _MiniTomlParser(text).parse()

    def test_scalars(self):
        data = self.parse('s = "hello"\nb = true\nf = false\ni = 42\npi = 3.5\n')
        assert data == {"s": "hello", "b": True, "f": False, "i": 42, "pi": 3.5}

    def test_comments(self):
        data = self.parse("# header\nkey = 1  # trailing\n")
        assert data == {"key": 1}

    def test_sections(self):
        data = self.parse("[a.b]\nx = 1\n[a]\ny = 2\n")
        assert data == {"a": {"b": {"x": 1}, "y": 2}}

    def test_arrays_single_line(self):
        data = self.parse('list = ["http", "https"]\n')
        assert data == {"list": ["http", "https"]}

    def test_arrays_multiline(self):
        data = self.parse('values = [\n  "a",\n  "b",  # comment\n]\n')
        assert data == {"values": ["a", "b"]}

    def test_string_escapes(self):
        data = self.parse(r'path = "a\"b\\c"')
        assert data == {"path": 'a"b\\c'}

    def test_literal_string(self):
        data = self.parse("path = 'C:\\raw'")
        assert data == {"path": "C:\\raw"}

    def test_error_on_garbage(self):
        with pytest.raises(ConfigError):
            self.parse("= broken")

    def test_error_unterminated_string(self):
        with pytest.raises(ConfigError):
            self.parse('x = "abc')

    def test_parses_shipped_default_toml(self):
        if sys.version_info >= (3, 11):
            import tomllib

            expected = tomllib.loads(DEFAULT_TOML.read_text(encoding="utf-8"))
            assert self.parse(DEFAULT_TOML.read_text(encoding="utf-8")) == expected


class TestLoadToml:
    def test_load_file(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text('[output]\nformat = "csv"\n', encoding="utf-8")
        assert load_toml(path) == {"output": {"format": "csv"}}

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError):
            load_toml(tmp_path / "missing.toml")

    def test_invalid_toml(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text("[broken\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_toml(path)


class TestConfigLoad:
    def test_defaults_without_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # avoid ./config/default.toml pickup
        config = Config.load()
        assert config.profile is Profile.STANDARD
        assert config.dedupe.mode is DedupeMode.NORMALIZED
        assert config.dedupe.hash_algorithm is HashAlgorithm.SHA256
        assert config.performance.backend == "memory"

    def test_load_custom_file(self, tmp_path):
        path = tmp_path / "custom.toml"
        path.write_text(
            'profile = "aggressive"\n[output]\nformat = "jsonl"\n'
            '[performance]\nworkers = 4\nbackend = "sqlite"\n',
            encoding="utf-8",
        )
        config = Config.load(path)
        assert config.profile is Profile.AGGRESSIVE
        assert config.output.format == "jsonl"
        assert config.performance.workers == 4
        assert config.performance.backend == "sqlite"

    def test_explicit_missing_path_raises(self, tmp_path):
        with pytest.raises(ConfigError):
            Config.load(tmp_path / "nope.toml")

    def test_unknown_enum_values_raise(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text('[dedupe]\nmode = "nonsense"\n', encoding="utf-8")
        with pytest.raises(ConfigError):
            Config.load(path)

    def test_boolean_type_enforced(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text("[normalization]\nstrip_www = 1\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            Config.load(path)

    def test_profiles_section(self, tmp_path):
        path = tmp_path / "p.toml"
        path.write_text("[profiles.aggressive]\nstrip_www = true\n", encoding="utf-8")
        config = Config.load(path)
        assert config.normalization_for("aggressive").strip_www is True
        assert config.normalization_for("standard").strip_www is False

    def test_to_dict_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data = Config.load().to_dict()
        assert data["profile"] == "standard"
        assert isinstance(data["normalization"], dict)


class TestDataFiles:
    def test_tracking_params_file_resolvable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)
        config = Config.load(DEFAULT_TOML)
        path = config.resolve_data_file("tracking_params.txt")
        assert path is not None and path.exists()
        assert "fbclid" in config.tracking_params()

    def test_extensions_file_resolvable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)
        config = Config.load(DEFAULT_TOML)
        mapping = config.extension_map()
        assert mapping["js"] == "js"
        assert mapping["pdf"] == "document"
        assert mapping["png"] == "image"

    def test_data_file_not_found_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = Config()
        config.config_path = None
        # no ./config dir, no package override for this name
        assert config.resolve_data_file("does_not_exist.xyz") is None
