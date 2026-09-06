"""Unit tests for statistics collection and rendering."""

from __future__ import annotations

from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline
from urluniq.reports.statistics import (
    ProcessingStats,
    RunResult,
    render_classification_summary,
    render_dashboard,
    render_top,
)


def _stats(urls: list[str]) -> ProcessingStats:
    stats = ProcessingStats()
    pipeline = URLPipeline(Config())
    for url in urls:
        stats.input_urls += 1
        record = pipeline.process(url)
        if record.error:
            stats.observe_invalid(record.raw, record.error)
        else:
            stats.observe_valid(record)
    return stats


class TestProcessingStats:
    def test_counters(self):
        stats = _stats(
            [
                "https://example.com/a?utm_source=x&ok=1",
                "HTTPS://EXAMPLE.com/A/",
                "https://example.com/b.js",
                "not a url",
                "gopher://x.com/",
            ]
        )
        assert stats.input_urls == 5
        assert stats.valid_urls == 3
        assert stats.invalid_urls == 2
        assert stats.errors["invalid scheme"] == 1
        assert stats.parameterized_urls == 1  # a?utm&ok
        assert stats.hosts["example.com"] == 3
        assert stats.domains["example.com"] == 3
        assert stats.categories["JS"] == 1
        assert stats.max_length > 0

    def test_examples_captured(self):
        stats = _stats(["HTTP://EXAMPLE.COM:80/", "https://example.com/x"])
        assert stats.examples[0]["original"] == "HTTP://EXAMPLE.COM:80/"
        assert stats.examples[0]["normalized"] == "http://example.com/"

    def test_largest_urls_capped(self):
        urls = [f"https://example.com/{'a' * n}" for n in range(1, 20)]
        stats = _stats(urls)
        assert len(stats.largest_urls) == 5
        assert stats.largest_urls[0][0] == max(length for length, _ in stats.largest_urls)

    def test_speed(self):
        stats = _stats(["https://example.com/"])
        assert stats.speed == 0.0  # no elapsed time recorded yet
        stats.elapsed_seconds = 0.5
        assert stats.speed > 0

    def test_to_dict(self):
        data = _stats(["https://example.com/a?x=1"]).to_dict()
        assert data["input_urls"] == 1
        assert data["top_hosts"][0][0] == "example.com"
        assert data["top_parameters"][0][0] == "x"


class TestRenderers:
    def test_dashboard_layout(self):
        stats = _stats(["https://example.com/", "HTTP://EXAMPLE.com/"])
        stats.duplicates = 1
        stats.unique_urls = 1
        stats.elapsed_seconds = 1.5
        dashboard = render_dashboard(stats)
        assert "URLUNIQ 2.0 REPORT" in dashboard
        assert "Input URLs          : 2" in dashboard
        assert "Duplicates" in dashboard
        assert "URLs/sec" in dashboard

    def test_classification_summary(self):
        stats = _stats(["https://example.com/a.js", "https://example.com/api/v1"])
        summary = render_classification_summary(stats)
        assert "JS" in summary and "API" in summary

    def test_top_rendering(self):
        stats = _stats(["https://example.com/a", "https://example.com/b"])
        block = render_top("hosts", stats.hosts)
        assert "Top hosts" in block
        assert "example.com" in block


class TestRunResult:
    def test_metadata_reproducibility(self):
        import sys

        metadata = RunResult.build_metadata(
            config_dict={"profile": "standard"},
            argv=["urluniq", "clean", "-i", "x.txt"],
            input_names=["x.txt"],
            output_name="y.txt",
            profile="standard",
            dedupe_mode="normalized",
            backend="memory",
            workers=1,
        )
        assert metadata["urluniq_version"]
        assert metadata["python_version"] == sys.version.split()[0]
        assert metadata["operating_system"]
        assert metadata["command_line"] == ["urluniq", "clean", "-i", "x.txt"]
        assert metadata["processing_timestamp"]
        assert metadata["profile"] == "standard"

    def test_to_dict(self):
        result = RunResult()
        result.stats = _stats(["https://example.com/"])
        result.duplicate_groups = [{"canonical": "x", "variants": ["x"], "count": 2}]
        data = result.to_dict()
        assert data["summary"]["input_urls"] == 1
        assert data["duplicates"][0]["count"] == 2
