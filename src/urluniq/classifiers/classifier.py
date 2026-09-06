"""The heuristic URL classifier."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from urluniq.classifiers.rules import (
    CATEGORY_LABELS,
    DEFAULT_RULES,
    EXTENSION_RULE_ORDER,
    ClassificationRule,
)
from urluniq.models import URLRecord


@dataclass(slots=True)
class Classification:
    """Result of classifying one URL record."""

    category: str
    label: str
    matched_rule: str = ""
    traits: list[str] = field(default_factory=list)


CustomRule = Callable[[URLRecord], "str | None"]


class URLClassifier:
    """Classifies URL records using keyword, parameter and extension rules."""

    def __init__(
        self,
        extension_map: dict[str, str],
        extra_rules: list[CustomRule] | None = None,
    ) -> None:
        self.extension_map = extension_map
        self.rules: tuple[ClassificationRule, ...] = DEFAULT_RULES
        self.custom_rules: list[CustomRule] = list(extra_rules or [])
        # Precompile keyword alternations once; classification is hot path.
        self._compiled = [
            (
                (
                    re.compile("|".join(re.escape(k) for k in rule.path_keywords))
                    if rule.path_keywords
                    else None
                ),
                set(p.lower() for p in rule.param_names),
                rule,
            )
            for rule in self.rules
        ]

    def classify(self, record: URLRecord) -> Classification:
        """Return the classification for ``record`` (heuristic)."""
        # Keywords are matched against host+path so rules like "api." also
        # catch host-shaped API signals (api.example.com).
        haystack = f"{record.host}{record.path or ''}".lower()
        params = {name.lower() for name in record.param_names}

        # Plugin-supplied rules run first.
        for custom in self.custom_rules:
            result = custom(record)
            if result:
                label = CATEGORY_LABELS.get(result, result)
                return Classification(result, label, matched_rule="custom rule")

        for keyword_re, param_set, rule in self._compiled:
            if keyword_re is not None and keyword_re.search(haystack):
                return Classification(rule.category, CATEGORY_LABELS[rule.category], rule.note)
            if param_set and params & param_set:
                return Classification(rule.category, CATEGORY_LABELS[rule.category], rule.note)

        ext_category = self.extension_map.get(record.extension, "")
        if ext_category in EXTENSION_RULE_ORDER:
            return Classification(
                ext_category, CATEGORY_LABELS[ext_category], f".{record.extension} extension"
            )

        if record.param_count > 0:
            return Classification(
                "parameterized", CATEGORY_LABELS["parameterized"], "carries query parameters"
            )
        if not record.extension:
            return Classification(
                "extensionless", CATEGORY_LABELS["extensionless"], "no file extension"
            )
        return Classification("unknown", CATEGORY_LABELS["unknown"], "no rule matched")

    def label(self, record: URLRecord) -> str:
        """Convenience: just the display label."""
        return self.classify(record).label
