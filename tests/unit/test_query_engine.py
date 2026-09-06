"""Unit tests for the smart query-parameter engine."""

from __future__ import annotations

from urluniq.config.loader import Config, NormalizationConfig, QueryConfig
from urluniq.normalizers.query import QueryEngine, join_pairs, split_pairs

TRACKING = {"utm_source", "utm_medium", "fbclid"}


def _engine(query_cfg: QueryConfig | None = None) -> QueryEngine:
    return QueryEngine(query_cfg or QueryConfig(), TRACKING)


def _norm(**kw) -> NormalizationConfig:
    return NormalizationConfig(**kw)


class TestPairHandling:
    def test_split_join_roundtrip(self):
        assert join_pairs(split_pairs("a=1&b=2&c")) == "a=1&b=2&c"

    def test_value_with_encoded_equals(self):
        pairs = split_pairs("next=%2Fadmin%3Fx%3D1")
        assert pairs == [["next", "%2Fadmin%3Fx%3D1"]]


class TestTrackingRemoval:
    def test_tracking_removed_when_enabled(self):
        result = _engine().process("q=1&utm_source=x", _norm(remove_tracking_params=True))
        assert result.query == "q=1"
        assert result.tracking_removed == 1
        assert "tracking parameters removed" in result.reasons

    def test_tracking_kept_when_disabled(self):
        result = _engine().process("q=1&utm_source=x", _norm())
        assert result.query == "q=1&utm_source=x"

    def test_case_insensitive_by_default(self):
        result = _engine().process("q=1&UTM_Source=x", _norm(remove_tracking_params=True))
        assert result.query == "q=1"

    def test_case_sensitive_matching(self):
        cfg = QueryConfig(case_sensitive_names=True)
        result = _engine(cfg).process("q=1&UTM_Source=x", _norm(remove_tracking_params=True))
        assert result.query == "q=1&UTM_Source=x"


class TestKeepDropLists:
    def test_keep_params_allowlist(self):
        cfg = QueryConfig(keep_params=["id", "page"])
        result = _engine(cfg).process("id=1&page=2&junk=3", _norm())
        assert result.query == "id=1&page=2"

    def test_drop_params_denylist(self):
        cfg = QueryConfig(drop_params=["debug"])
        result = _engine(cfg).process("a=1&debug=1", _norm())
        assert result.query == "a=1"

    def test_drop_list_case_insensitive(self):
        cfg = QueryConfig(drop_params=["debug"])
        result = _engine(cfg).process("a=1&DEBUG=trace", _norm())
        assert result.query == "a=1"


class TestDuplicateParams:
    def test_keep_first(self):
        result = _engine().process("id=1&id=2", _norm(dedupe_query_params=True))
        assert result.query == "id=1"

    def test_keep_last(self):
        cfg = QueryConfig(duplicate_keep="last")
        result = _engine(cfg).process("id=1&id=2", _norm(dedupe_query_params=True))
        assert result.query == "id=2"

    def test_duplicate_detection_flag_only(self):
        result = _engine().process("id=1&id=2", _norm())
        assert result.query == "id=1&id=2"  # preserved when configured


class TestEmptyParams:
    def test_remove_empty_names_and_values(self):
        result = _engine().process("=x&a=&b=2", _norm(remove_empty_params=True))
        assert result.query == "b=2"

    def test_empty_kept_by_default(self):
        result = _engine().process("a=&b=2", _norm())
        assert result.query == "a=&b=2"


class TestSorting:
    def test_sort_by_decoded_name(self):
        result = _engine().process("z=1&a=2&m=3", _norm(sort_query_params=True))
        assert result.query == "a=2&m=3&z=1"

    def test_no_sort_in_safe(self):
        result = _engine().process("z=1&a=2", _norm(sort_query_params=False))
        assert result.query == "z=1&a=2"

    def test_original_encoding_preserved_after_sort(self):
        result = _engine().process("b=%2Fx&a=%2Fy", _norm(sort_query_params=True))
        assert result.query == "a=%2Fy&b=%2Fx"


class TestSessionDetection:
    def test_session_params_detected(self):
        engine = _engine()
        assert engine.is_session("jsessionid")
        assert engine.is_session("PHPSESSID")
        assert engine.is_session("csrf_token")
        assert engine.is_session("session_id")
        assert not engine.is_session("page")

    def test_tracking_detection(self):
        engine = _engine()
        assert engine.is_tracking("utm_source")
        assert not engine.is_tracking("q")


class TestConfigTrackingList:
    def test_tracking_params_from_config_and_file(self, tmp_path):
        config = Config()
        config.config_path = tmp_path / "default.toml"
        (tmp_path / "tracking_params.txt").write_text("zzz_custom\n")
        config.query.tracking_params = ["yyy_extra"]
        tracking = config.tracking_params()
        assert "zzz_custom" in tracking
        assert "yyy_extra" in tracking
        assert "utm_source" in tracking  # built-in fallback

    def test_add_tracking_params_runtime(self):
        config = Config()
        config.add_tracking_params({"My_Custom_Tracker"})
        assert "my_custom_tracker" in config.tracking_params()
