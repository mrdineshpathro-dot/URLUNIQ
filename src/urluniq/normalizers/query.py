"""Query-string processing engine.

Implements the "smart query parameter engine": tracking-parameter removal,
allow/deny lists, duplicate-parameter handling, empty-parameter removal and
parameter ordering - all while preserving the original percent-encoding of
values whenever no change is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

from urluniq.config.loader import NormalizationConfig, QueryConfig
from urluniq.constants import (
    QUERY_SAFE_RAW,
    REASON_DUP_PARAMS,
    REASON_EMPTY_PARAMS_REMOVED,
    REASON_PARAM_DROPPED,
    REASON_PARAM_KEPT,
    REASON_PARAMS_SORTED,
    REASON_PERCENT_NORMALIZED,
    REASON_TRACKING_REMOVED,
)

# Raw-safe characters for an individual parameter name/value (delimiters
# '&' and '=' are excluded because they were split out beforehand).
PAIR_SAFE_RAW = QUERY_SAFE_RAW - {"&", "="}


@dataclass(slots=True)
class QueryResult:
    """Outcome of query processing."""

    query: str
    reasons: list[str] = field(default_factory=list)
    tracking_removed: int = 0
    param_names: list[str] = field(default_factory=list)


def split_pairs(query: str) -> list[list[str]]:
    """Split a raw query string into ``[name, value]`` pairs (no decoding)."""
    if not query:
        return []
    return [p.split("=", 1) if "=" in p else [p] for p in query.split("&")]


def join_pairs(pairs: list[list[str]]) -> str:
    """Re-join raw pairs into a query string, preserving encoding."""
    return "&".join("=".join(pair) if len(pair) == 2 else pair[0] for pair in pairs)


def decode_name(raw: str) -> str:
    """Decode a raw parameter name for comparison purposes."""
    return unquote(raw).lower()


class QueryEngine:
    """Applies query-parameter rules from the configuration."""

    def __init__(self, query_config: QueryConfig, tracking_params: set[str]) -> None:
        self.cfg = query_config
        self.tracking = {t.lower() for t in tracking_params}

    # -- matching helpers -------------------------------------------------

    def _matches(self, raw_name: str, names: set[str]) -> bool:
        name = raw_name if self.cfg.case_sensitive_names else raw_name.lower()
        return name in names

    def is_tracking(self, raw_name: str) -> bool:
        return self._matches(raw_name, self.tracking)

    def is_session(self, raw_name: str) -> bool:
        from urluniq.constants import SESSION_PARAM_HINTS

        name = raw_name if self.cfg.case_sensitive_names else raw_name.lower()
        return any(hint in name for hint in SESSION_PARAM_HINTS)

    # -- main entry ---------------------------------------------------------

    def process(self, query: str, norm_config: NormalizationConfig) -> QueryResult:
        """Process one query string according to normalization config."""
        reasons: list[str] = []
        tracking_removed = 0
        if not query:
            return QueryResult(query="", reasons=reasons, param_names=[])

        from urluniq.normalizers.base import normalize_percent_encoding

        pairs = split_pairs(query)
        # Percent-encoding normalization per component, never touching the
        # '&' / '=' delimiters that were split out above.
        encoded_pairs = [
            (
                [
                    normalize_percent_encoding(
                        p[0], PAIR_SAFE_RAW, encode_non_ascii=norm_config.encode_non_ascii
                    ),
                    normalize_percent_encoding(
                        p[1], PAIR_SAFE_RAW, encode_non_ascii=norm_config.encode_non_ascii
                    ),
                ]
                if len(p) == 2
                else [
                    normalize_percent_encoding(
                        p[0], PAIR_SAFE_RAW, encode_non_ascii=norm_config.encode_non_ascii
                    ),
                ]
            )
            for p in pairs
        ]
        if join_pairs(encoded_pairs) != query:
            reasons.append(REASON_PERCENT_NORMALIZED)

        # Fast path: when no parameter rule is active and the encoding did
        # not change, keep the original string untouched.
        if not (
            self.cfg.keep_params
            or self.cfg.drop_params
            or norm_config.remove_tracking_params
            or norm_config.remove_empty_params
            or norm_config.dedupe_query_params
            or norm_config.sort_query_params
        ):
            param_names = [decode_name(p[0]) for p in encoded_pairs]
            return QueryResult(query=query, reasons=reasons, param_names=param_names)

        # 1. keep/deny lists ------------------------------------------------
        if self.cfg.keep_params:
            kept = [p for p in encoded_pairs if self._matches(p[0], set(self.cfg.keep_params))]
            if len(kept) != len(encoded_pairs):
                reasons.append(REASON_PARAM_KEPT)
            encoded_pairs = kept
        if self.cfg.drop_params:
            filtered = [
                p for p in encoded_pairs if not self._matches(p[0], set(self.cfg.drop_params))
            ]
            if len(filtered) != len(encoded_pairs):
                reasons.append(REASON_PARAM_DROPPED)
            encoded_pairs = filtered

        # 2. tracking removal -------------------------------------------------
        if norm_config.remove_tracking_params:
            before = len(encoded_pairs)
            encoded_pairs = [p for p in encoded_pairs if not self.is_tracking(p[0])]
            tracking_removed = before - len(encoded_pairs)
            if tracking_removed:
                reasons.append(REASON_TRACKING_REMOVED)

        # 3. empty parameters ---------------------------------------------------
        if norm_config.remove_empty_params:
            kept = [
                p
                for p in encoded_pairs
                if decode_name(p[0]) != "" and not (len(p) == 2 and p[1] == "")
            ]
            if len(kept) != len(encoded_pairs):
                reasons.append(REASON_EMPTY_PARAMS_REMOVED)
            encoded_pairs = kept

        # 4. duplicate parameters -------------------------------------------------
        if norm_config.dedupe_query_params and encoded_pairs:
            seen: set[str] = set()
            unique: list[list[str]] = []
            source = reversed(encoded_pairs) if self.cfg.duplicate_keep == "last" else encoded_pairs
            for pair in source:
                key = p_name(pair, self.cfg.case_sensitive_names)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(pair)
            if self.cfg.duplicate_keep == "last":
                unique.reverse()
            if len(unique) != len(encoded_pairs):
                reasons.append(REASON_DUP_PARAMS)
            encoded_pairs = unique

        # 5. ordering ---------------------------------------------------------
        if norm_config.sort_query_params and encoded_pairs:
            encoded_pairs = sorted(
                encoded_pairs,
                key=lambda p: (decode_name(p[0]), decode_name(p[1]) if len(p) == 2 else ""),
            )
            if join_pairs(encoded_pairs) != query:
                reasons.append(REASON_PARAMS_SORTED)

        param_names = [decode_name(p[0]) for p in encoded_pairs]
        return QueryResult(
            query=join_pairs(encoded_pairs),
            reasons=reasons,
            tracking_removed=tracking_removed,
            param_names=param_names,
        )


def p_name(pair: list[str], case_sensitive: bool) -> str:
    """Comparison key for a raw parameter pair."""
    name = unquote(pair[0])
    return name if case_sensitive else name.lower()
