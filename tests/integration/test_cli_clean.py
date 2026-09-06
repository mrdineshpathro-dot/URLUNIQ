"""Integration tests for the clean subcommand."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from tests.conftest import FakeStdin
from urluniq.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run(argv: list[str]) -> int:
    return main(argv)


class TestBasicClean:
    def test_clean_to_file(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        code = _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet"])
        assert code == 0
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines == [
            "http://example.com/",
            "https://example.com/",
            "https://example.com/search/?q=1&utm_source=test",
            "https://example.com/search/?q=1",
        ]

    def test_clean_to_stdout(self, urls_file: Path, capsys):
        code = _run(["clean", "-i", str(urls_file), "--quiet"])
        assert code == 0
        assert capsys.readouterr().out.count("\n") == 4

    def test_dashboard_with_stats(self, urls_file: Path, tmp_path: Path, capsys):
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--stats"])
        captured = capsys.readouterr()
        assert "URLUNIQ 2.0 REPORT" in captured.out
        assert "Input URLs          : 8" in captured.out
        assert "Unique URLs         : 4" in captured.out

    def test_remove_tracking_flag(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--remove-tracking"])
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines == [
            "http://example.com/",
            "https://example.com/",
            "https://example.com/search/?q=1",
        ]

    def test_profile_safe_preserves_variants(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("HTTP://EXAMPLE.com/#frag\nhttp://example.com\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--profile", "safe"])
        assert len(out.read_text(encoding="utf-8").splitlines()) == 2

    def test_classify_summary(self, urls_file: Path, tmp_path: Path, capsys):
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--classify"])
        captured = capsys.readouterr()
        assert "Search" in captured.out


class TestOutputFormats:
    def test_csv_output(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.csv"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet"])
        rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
        assert rows[0]["url"] == "HTTP://EXAMPLE.COM:80/"
        assert rows[0]["normalized_url"] == "http://example.com/"
        assert rows[0]["category"]

    def test_jsonl_output(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.jsonl"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet"])
        records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert len(records) == 4
        assert set(records[0]) == {"url", "normalized_url", "canonical_url", "category"}

    def test_json_output(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.json"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet"])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload, list) and len(payload) == 4

    def test_explain_adds_changes(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.jsonl"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--explain"])
        records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert all("changes" in record for record in records)
        assert any(record["changes"] for record in records)


class TestInputFormats:
    def test_csv_input(self, tmp_path: Path):
        source = tmp_path / "u.csv"
        source.write_text("url,src\nhttps://a.com/x?b=2&a=1,c\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/x/?a=1&b=2"]

    def test_csv_input_url_column(self, tmp_path: Path):
        source = tmp_path / "u.csv"
        source.write_text("id,link\n1,https://a.com/\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--url-column", "link"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/"]

    def test_json_input(self, tmp_path: Path):
        source = tmp_path / "u.json"
        source.write_text(json.dumps(["https://a.com/", "https://a.com"]), encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/"]

    def test_json_input_custom_field(self, tmp_path: Path):
        source = tmp_path / "u.json"
        source.write_text(json.dumps([{"href": "https://a.com/"}]), encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--json-field", "href"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/"]

    def test_jsonl_input(self, tmp_path: Path):
        source = tmp_path / "u.jsonl"
        source.write_text(
            '{"url":"https://example.com"}\n{"url":"https://example.com/test"}\n',
            encoding="utf-8",
        )
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == [
            "https://example.com/",
            "https://example.com/test/",
        ]

    def test_stdin(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(sys, "stdin", FakeStdin("https://a.com/\nhttps://a.com\n"))
        out = tmp_path / "clean.txt"
        _run(["clean", "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/"]

    def test_stdin_dash(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "stdin", FakeStdin("https://a.com/\n"))
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", "-", "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/"]

    def test_multiple_inputs_merge(self, tmp_path: Path):
        first = tmp_path / "a.txt"
        second = tmp_path / "b.txt"
        first.write_text("https://a.com/\n", encoding="utf-8")
        second.write_text("https://a.com/\nhttps://b.com/\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(first), "-i", str(second), "-o", str(out), "--quiet"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/", "https://b.com/"]

    def test_input_dir_recursive(self, tmp_path: Path):
        sub = tmp_path / "nested"
        sub.mkdir()
        (tmp_path / "a.txt").write_text("https://a.com/\n", encoding="utf-8")
        (sub / "b.txt").write_text("https://b.com/\n", encoding="utf-8")
        (sub / "c.bak").write_text("https://c.com/\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(
            [
                "clean",
                "--input-dir",
                str(tmp_path),
                "--recursive",
                "--include",
                "*.txt",
                "--exclude",
                "*.bak",
                "-o",
                str(out),
                "--quiet",
            ]
        )
        lines = out.read_text(encoding="utf-8").splitlines()
        assert "https://a.com/" in lines and "https://b.com/" in lines
        assert "https://c.com/" not in lines

    def test_examples_directory(self, tmp_path: Path):
        out = tmp_path / "clean.txt"
        code = _run(["clean", "-i", str(EXAMPLES / "urls.txt"), "-o", str(out), "--quiet"])
        assert code == 0
        assert len(out.read_text(encoding="utf-8").splitlines()) == 4


class TestFiltersCLI:
    def test_exclude_extension(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://a.com/x.jpg\nhttps://a.com/y.js\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--exclude-extension", "jpg"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/y.js"]

    def test_include_host(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://keep.example.com/a\nhttps://drop.com/b\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--include-host",
                "keep.example.com",
            ]
        )
        assert out.read_text(encoding="utf-8").splitlines() == ["https://keep.example.com/a/"]

    def test_domain_scope(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text(
            "https://example.com/a\nhttps://api.example.com/b\nhttps://other.com/c\n",
            encoding="utf-8",
        )
        out = tmp_path / "clean.txt"
        _run(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--domain",
                "example.com",
                "--include-subdomains",
            ]
        )
        assert out.read_text(encoding="utf-8").splitlines() == [
            "https://example.com/a/",
            "https://api.example.com/b/",
        ]

    def test_exclude_regex(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text(
            "https://a.com/wp-admin/settings\nhttps://a.com/public\n", encoding="utf-8"
        )
        out = tmp_path / "clean.txt"
        _run(
            ["clean", "-i", str(source), "-o", str(out), "--quiet", "--exclude-regex", r"/wp-admin"]
        )
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/public/"]

    def test_keep_and_drop_params(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://a.com/p?id=1&debug=1&extra=2\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--keep-param",
                "id",
                "--keep-param",
                "extra",
            ]
        )
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/p/?extra=2&id=1"]

    def test_drop_param(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://a.com/p?token=abc&page=2\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--drop-param", "token"])
        assert out.read_text(encoding="utf-8").splitlines() == ["https://a.com/p/?page=2"]


class TestExtras:
    def test_invalid_output(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://a.com/\nnot a url\ngopher://x/\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        invalid = tmp_path / "invalid.txt"
        _run(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--invalid-output",
                str(invalid),
            ]
        )
        lines = invalid.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("not a url\t")

    def test_duplicates_output_txt(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        dups = tmp_path / "dups.txt"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--duplicates-output",
                str(dups),
            ]
        )
        text = dups.read_text(encoding="utf-8")
        assert "CANONICAL:" in text and "VARIANTS:" in text and "COUNT:" in text
        assert "https://example.com/#home" in text

    def test_duplicates_output_json(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        dups = tmp_path / "dups.json"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--duplicates-output",
                str(dups),
            ]
        )
        payload = json.loads(dups.read_text(encoding="utf-8"))
        assert payload and all({"canonical", "variants", "count"} <= set(g) for g in payload)

    def test_endpoint_groups(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        groups = tmp_path / "groups.txt"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--group-by-endpoint",
                str(groups),
            ]
        )
        text = groups.read_text(encoding="utf-8")
        assert "[example.com/search/]" in text
        assert "[example.com/]" in text

    def test_group_host(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://a.com/x\nhttps://a.com/y\nhttps://b.com/z\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        groups = tmp_path / "hosts.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--group-host", str(groups)])
        text = groups.read_text(encoding="utf-8")
        assert "[a.com] (2 URLs)" in text
        assert "[b.com] (1 URL)" in text

    def test_features_export(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        features = tmp_path / "features.jsonl"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--extract-features",
                "--features-output",
                str(features),
            ]
        )
        records = [json.loads(line) for line in features.read_text(encoding="utf-8").splitlines()]
        # Features are exported for each *unique* URL (4 of the 8 input lines).
        assert len(records) == 4
        first = records[0]
        assert first["scheme"] == "http"
        assert first["host"] == "example.com"
        assert first["registrable_domain"] == "example.com"
        assert "query_param_count" in first and "path_depth" in first

    def test_redact_userinfo(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://admin:secret@a.com/x\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--redact-userinfo"])
        text = out.read_text(encoding="utf-8")
        assert "secret" not in text
        assert "[REDACTED]" in text

    def test_sort_url(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--sort", "url"])
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines == sorted(lines)

    def test_dedupe_modes_cli(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text(
            "https://a.com/x?q=1\nhttps://a.com/x?q=2\nhttps://b.com/y\n",
            encoding="utf-8",
        )
        out = tmp_path / "clean.txt"
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--dedupe", "path"])
        assert len(out.read_text(encoding="utf-8").splitlines()) == 2
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--dedupe", "host"])
        assert len(out.read_text(encoding="utf-8").splitlines()) == 2
        _run(["clean", "-i", str(source), "-o", str(out), "--quiet", "--dedupe", "normalized"])
        assert len(out.read_text(encoding="utf-8").splitlines()) == 3

    def test_hash_option(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        code = _run(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--hash", "sha1"])
        assert code == 0
        assert len(out.read_text(encoding="utf-8").splitlines()) == 4

    def test_log_file_writes(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        log = tmp_path / "app.log"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--log",
                str(log),
                "--verbose",
            ]
        )
        assert log.exists()
        assert "startup" in log.read_text(encoding="utf-8")

    def test_log_json_format(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        log = tmp_path / "app.jsonl"
        _run(
            [
                "clean",
                "-i",
                str(urls_file),
                "-o",
                str(out),
                "--quiet",
                "--log",
                str(log),
                "--log-format",
                "json",
                "--verbose",
            ]
        )
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        record = json.loads(lines[0])
        assert "message" in record and "level" in record

    def test_log_redacts_credentials(self, tmp_path: Path):
        source = tmp_path / "u.txt"
        source.write_text("https://user:hunter2@a.com/x\n", encoding="utf-8")
        out = tmp_path / "clean.txt"
        log = tmp_path / "app.log"
        _run(
            ["clean", "-i", str(source), "-o", str(out), "--quiet", "--log", str(log), "--verbose"]
        )
        assert "hunter2" not in log.read_text(encoding="utf-8")
