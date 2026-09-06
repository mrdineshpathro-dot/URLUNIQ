"""Unit tests for input parsers: TXT, CSV, JSON, JSONL, stdin, discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import FakeStdin
from urluniq.exceptions import InputError
from urluniq.parsers import detect_format, discover_files, iter_input
from urluniq.parsers.csv import iter_csv
from urluniq.parsers.json import iter_json
from urluniq.parsers.jsonl import iter_jsonl
from urluniq.parsers.txt import iter_txt


class TestTxt:
    def test_lines_and_comments(self, tmp_path):
        path = tmp_path / "u.txt"
        path.write_text(
            "https://a.com/\n\n# comment\nhttps://b.com/\n  https://c.com/  \n",
            encoding="utf-8",
        )
        assert list(iter_txt(path)) == ["https://a.com/", "https://b.com/", "https://c.com/"]

    def test_missing_file(self, tmp_path):
        with pytest.raises(InputError):
            list(iter_txt(tmp_path / "missing.txt"))


class TestCsv:
    def test_url_header_autodetected(self, tmp_path):
        path = tmp_path / "u.csv"
        path.write_text("url,source\nhttps://a.com/,x\nhttps://b.com/,y\n", encoding="utf-8")
        assert list(iter_csv(path)) == ["https://a.com/", "https://b.com/"]

    def test_named_column(self, tmp_path):
        path = tmp_path / "u.csv"
        path.write_text("id,link\n1,https://a.com/\n2,https://b.com/\n", encoding="utf-8")
        assert list(iter_csv(path, "link")) == ["https://a.com/", "https://b.com/"]

    def test_column_index(self, tmp_path):
        path = tmp_path / "u.csv"
        path.write_text("1,https://a.com/\n2,https://b.com/\n", encoding="utf-8")
        assert list(iter_csv(path, 1)) == ["https://a.com/", "https://b.com/"]

    def test_headerless_first_column(self, tmp_path):
        path = tmp_path / "u.csv"
        path.write_text("https://a.com/\nhttps://b.com/\n", encoding="utf-8")
        assert list(iter_csv(path)) == ["https://a.com/", "https://b.com/"]

    def test_unknown_named_column(self, tmp_path):
        path = tmp_path / "u.csv"
        path.write_text("url\nhttps://a.com/\n", encoding="utf-8")
        with pytest.raises(InputError):
            list(iter_csv(path, "missing"))


class TestJson:
    def test_list_of_strings(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps(["https://a.com/", "https://b.com/"]), encoding="utf-8")
        assert list(iter_json(path)) == ["https://a.com/", "https://b.com/"]

    def test_list_of_objects(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(
            json.dumps([{"url": "https://a.com/", "x": 1}, {"url": "https://b.com/"}]),
            encoding="utf-8",
        )
        assert list(iter_json(path)) == ["https://a.com/", "https://b.com/"]

    def test_custom_field(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps([{"href": "https://a.com/"}]), encoding="utf-8")
        assert list(iter_json(path, "href")) == ["https://a.com/"]

    def test_urls_wrapper_object(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text(json.dumps({"urls": ["https://a.com/"]}), encoding="utf-8")
        assert list(iter_json(path)) == ["https://a.com/"]

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "u.json"
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(InputError):
            list(iter_json(path))


class TestJsonl:
    def test_objects_per_line(self, tmp_path):
        path = tmp_path / "u.jsonl"
        path.write_text(
            '{"url":"https://example.com"}\n{"url":"https://example.com/test"}\n',
            encoding="utf-8",
        )
        assert list(iter_jsonl(path)) == ["https://example.com", "https://example.com/test"]

    def test_comment_lines_skipped(self, tmp_path):
        path = tmp_path / "u.jsonl"
        path.write_text('# note\n{"url":"https://a.com/"}\n', encoding="utf-8")
        assert list(iter_jsonl(path)) == ["https://a.com/"]

    def test_missing_field(self, tmp_path):
        path = tmp_path / "u.jsonl"
        path.write_text('{"href":"https://a.com/"}\n', encoding="utf-8")
        with pytest.raises(InputError):
            list(iter_jsonl(path))


class TestFormatDetection:
    @pytest.mark.parametrize(
        ("name", "fmt"),
        [
            ("u.txt", "txt"),
            ("u.csv", "csv"),
            ("u.json", "json"),
            ("u.jsonl", "jsonl"),
            ("u.ndjson", "jsonl"),
            ("u.weird", "txt"),
        ],
    )
    def test_detect(self, name, fmt):
        assert detect_format(Path(name)) == fmt


class TestDiscovery:
    def test_directory_expansion(self, tmp_path):
        (tmp_path / "a.txt").write_text("https://a.com/")
        (tmp_path / "b.txt").write_text("https://b.com/")
        files = discover_files([tmp_path])
        assert [f.name for f in files] == ["a.txt", "b.txt"]

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.txt").write_text("x")
        (sub / "nested.txt").write_text("x")
        files = discover_files([tmp_path], recursive=True)
        assert len(files) == 2
        files = discover_files([tmp_path], recursive=False)
        assert len(files) == 1

    def test_include_exclude_patterns(self, tmp_path):
        (tmp_path / "keep.txt").write_text("x")
        (tmp_path / "drop.bak").write_text("x")
        files = discover_files([tmp_path], include=["*.txt"], exclude=["*.bak"])
        assert [f.name for f in files] == ["keep.txt"]

    def test_glob_path(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        files = discover_files([tmp_path / "*.txt"])
        assert len(files) == 1

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(InputError):
            discover_files([tmp_path / "nope.txt"])


class TestStdin:
    def test_stdin_txt(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", FakeStdin("https://a.com/\nhttps://b.com/\n"))
        assert list(iter_input(None, "txt")) == ["https://a.com/", "https://b.com/"]

    def test_unsupported_format(self, tmp_path):
        with pytest.raises(InputError):
            list(iter_input(tmp_path / "u.parquet", "parquet"))
