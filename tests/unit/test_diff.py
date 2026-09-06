"""Unit tests for the differential analysis engine and exports."""

from __future__ import annotations

import csv
import json

import pytest

from urluniq.config.loader import Config
from urluniq.core.diff import (
    DiffEntry,
    DiffResult,
    compute_diff,
    export_csv,
    export_json,
    export_txt,
)
from urluniq.core.pipeline import URLPipeline

OLD = [
    "https://example.com/",
    "https://example.com/search?q=1",
    "https://api.example.com/v1/users?page=1",
    "https://example.com/static/app.js",
    "http://EXAMPLE.com:80/legacy/",
]

NEW = [
    "https://example.com/",
    "https://example.com/search?q=2",
    "https://api.example.com/v1/users?page=1",
    "https://example.com/static/app.js",
    "https://example.com/legacy/",
    "https://new.example.com/panel",
]


@pytest.fixture
def result() -> DiffResult:
    pipeline = URLPipeline(Config())
    return compute_diff(pipeline, OLD, NEW)


class TestComputeDiff:
    def test_new(self, result):
        new = {entry.new_url for entry in result.new}
        assert "https://example.com/search?q=2" in new
        assert "https://new.example.com/panel" in new

    def test_removed(self, result):
        removed = {entry.old_url for entry in result.removed}
        assert "https://example.com/search?q=1" in removed

    def test_unchanged(self, result):
        assert result.unchanged == 3  # /, users?page=1, app.js

    def test_changed_detected_for_normalized_variant(self, result):
        # http://EXAMPLE.com:80/legacy/ (old) vs https://example.com/legacy/ (new)
        # differ in scheme so they are NEW+REMOVED, but /search q=1 vs q=2 are too.
        # Use a targeted pair for the CHANGED bucket:
        pipeline = URLPipeline(Config())
        diff = compute_diff(
            pipeline,
            ["https://example.com/x?q=1&flag=on"],
            ["https://example.com/x/?flag=on&q=1"],
        )
        assert diff.unchanged == 0
        assert len(diff.changed) == 1
        assert diff.changed[0].canonical == "https://example.com/x/?flag=on&q=1"

    def test_summary_lines(self, result):
        lines = result.summary_lines()
        assert lines[0].startswith("New:")
        assert "Unchanged:" in lines[2]
        assert "Changed:" in lines[3]

    def test_invalid_urls_ignored(self):
        pipeline = URLPipeline(Config())
        diff = compute_diff(pipeline, ["not a url"], ["gopher://x/"])
        assert not diff.new and not diff.removed


class TestDiffExports:
    def test_json(self, tmp_path, result):
        path = tmp_path / "d.json"
        export_json(path, result)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["summary"]["unchanged"] == result.unchanged
        assert isinstance(data["new"], list)

    def test_csv(self, tmp_path, result):
        path = tmp_path / "d.csv"
        export_csv(path, result)
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        statuses = {row["status"] for row in rows}
        assert "new" in statuses and "removed" in statuses

    def test_txt(self, tmp_path, result):
        path = tmp_path / "d.txt"
        export_txt(path, result)
        text = path.read_text(encoding="utf-8")
        assert "NEW URLS" in text and "REMOVED URLS" in text
        assert "UNCHANGED" in text

    def test_entry_dataclass(self):
        entry = DiffEntry("canonical", "old", "new")
        assert (entry.canonical, entry.old_url, entry.new_url) == ("canonical", "old", "new")
