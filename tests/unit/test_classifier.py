"""Unit tests for the heuristic URL classifier."""

from __future__ import annotations

import pytest

from urluniq.classifiers.classifier import URLClassifier
from urluniq.classifiers.rules import CATEGORY_LABELS, DEFAULT_RULES
from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline


def _classify(url: str, extra_rules=None) -> str:
    config = Config()
    classifier = URLClassifier(config.extension_map(), extra_rules=extra_rules)
    pipeline = URLPipeline(config, classifier=classifier)
    return pipeline.process(url).category


@pytest.mark.parametrize(
    ("url", "label"),
    [
        ("https://example.com/api/v1/users", "API"),
        ("https://api.example.com/users", "API"),
        ("https://example.com/graphql", "API"),
        ("https://example.com/data.json", "API"),
        ("https://example.com/static/app.js", "JS"),
        ("https://example.com/static/style.css", "CSS"),
        ("https://example.com/img/logo.png", "Image"),
        ("https://example.com/reports/q3.pdf", "Document"),
        ("https://example.com/login", "Auth"),
        ("https://example.com/wp-login.php", "Auth"),
        ("https://example.com/signin?next=/", "Auth"),
        ("https://example.com/logout", "Logout"),
        ("https://example.com/search?q=test", "Search"),
        ("https://example.com/results?query=x", "Search"),
        ("https://example.com/downloads/file", "Download"),
        ("https://example.com/upload", "Upload"),
        ("https://example.com/cdn/fonts.woff2", "Static"),
        ("https://example.com/about.html", "HTML"),
        ("https://example.com/page.php", "HTML"),
        ("https://example.com/go?url=https://other.com", "Redirect"),
        ("https://example.com/next?returnurl=/home", "Redirect"),
        ("https://example.com/profile?user=42", "Parameterized"),
        ("https://example.com/plain/page", "Extensionless"),
        ("https://example.com/file.xyz", "Unknown"),
    ],
)
def test_categories(url: str, label: str):
    assert _classify(url) == label, url


def test_priority_logout_over_auth():
    # logout rule runs before auth
    assert _classify("https://example.com/auth/logout") == "Logout"


def test_custom_plugin_rule_runs_first():
    def sitemap_rule(record):
        if "sitemap" in record.path:
            return "Sitemap"
        return None

    assert _classify("https://example.com/sitemap.xml", extra_rules=[sitemap_rule]) == "Sitemap"


def test_labels_complete():
    assert CATEGORY_LABELS["api"] == "API"
    assert CATEGORY_LABELS["parameterized"] == "Parameterized"
    for rule in DEFAULT_RULES:
        assert rule.category in CATEGORY_LABELS


def test_classification_is_heuristic():
    # A .json path with /search/ keyword classifies as Search, not API -
    # documented heuristic-priority behaviour.
    assert _classify("https://example.com/search/data.json") == "Search"
