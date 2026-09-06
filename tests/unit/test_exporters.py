"""Unit tests for exporters: TXT, CSV, JSON, JSONL."""

from __future__ import annotations

import csv
import io
import json

from urluniq.config.loader import Config
from urluniq.core.pipeline import URLPipeline
from urluniq.exporters import build_exporter
from urluniq.exporters.json import record_to_dict


def _record(url: str = "HTTP://EXAMPLE.COM:80/x#f"):
    record = URLPipeline(Config()).process(url)
    assert not record.error
    return record


class TestTxt:
    def test_writes_normalized(self):
        buffer = io.StringIO()
        exporter = build_exporter("txt", buffer)
        exporter.write(_record())
        exporter.finish()
        assert buffer.getvalue() == "http://example.com/x/\n"


class TestCsv:
    def test_header_and_rows(self):
        buffer = io.StringIO()
        exporter = build_exporter("csv", buffer, csv_header=True)
        exporter.write(_record())
        exporter.finish()
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        assert rows[0] == ["url", "normalized_url", "canonical_url", "category"]
        assert rows[1][0] == "HTTP://EXAMPLE.COM:80/x#f"
        assert rows[1][1] == "http://example.com/x/"

    def test_explain_adds_changes_column(self):
        buffer = io.StringIO()
        exporter = build_exporter("csv", buffer, explain=True)
        exporter.write(_record())
        exporter.finish()
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        assert rows[0][-1] == "changes"
        assert "fragment removed" in rows[1][-1]

    def test_no_header(self):
        buffer = io.StringIO()
        exporter = build_exporter("csv", buffer, csv_header=False)
        exporter.write(_record())
        exporter.finish()
        assert "url,normalized" not in buffer.getvalue()


class TestJsonShapes:
    def test_record_dict_shape(self):
        data = record_to_dict(_record())
        assert set(data) == {"url", "normalized_url", "canonical_url", "category"}
        assert data["url"] == "HTTP://EXAMPLE.COM:80/x#f"

    def test_json_exporter_array(self):
        buffer = io.StringIO()
        exporter = build_exporter("json", buffer)
        exporter.write(_record())
        exporter.write(_record("https://example.com/y"))
        exporter.finish()
        payload = json.loads(buffer.getvalue())
        assert isinstance(payload, list) and len(payload) == 2

    def test_jsonl_exporter_lines(self):
        buffer = io.StringIO()
        exporter = build_exporter("jsonl", buffer)
        exporter.write(_record())
        exporter.finish()
        lines = buffer.getvalue().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["url"] == "HTTP://EXAMPLE.COM:80/x#f"
