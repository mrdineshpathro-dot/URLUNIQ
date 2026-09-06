"""Integration tests for report generation and the SQLite backend via CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from urluniq.cli import main


class TestReports:
    def test_html_report_standalone(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        report = tmp_path / "report.html"
        assert (
            main(
                ["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--report", str(report)]
            )
            == 0
        )
        html_text = report.read_text(encoding="utf-8")
        assert html_text.startswith("<!DOCTYPE html>")
        assert "URLUNIQ 2.0 REPORT" in html_text
        assert "urluniq_version" in html_text or "Reproducibility" in html_text
        assert "<style>" in html_text
        # No external network resources: inline CSS only, no external links.
        assert 'src="http' not in html_text
        assert "<link" not in html_text
        assert "@import" not in html_text
        assert "https://github.com/mrdineshpathro-dot" in html_text

    def test_json_report_reproducibility(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        report = tmp_path / "report.json"
        main(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
        meta = payload["metadata"]
        for key in (
            "urluniq_version",
            "python_version",
            "operating_system",
            "profile",
            "configuration",
            "command_line",
            "processing_timestamp",
            "input_files",
            "output_file",
        ):
            assert key in meta, key
        assert payload["summary"]["unique_urls"] == 4

    def test_csv_report_sections(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "clean.txt"
        report = tmp_path / "report.csv"
        main(["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--report", str(report)])
        text = report.read_text(encoding="utf-8")
        assert text.startswith("section,key,value")
        assert "summary,input_urls,8" in text
        assert "hosts,example.com" in text


class TestSQLiteBackend:
    def _source(self, tmp_path: Path) -> Path:
        source = tmp_path / "u.txt"
        source.write_text(
            "\n".join(
                [
                    "https://a.com/x?i=1",
                    "https://a.com/x?i=2",
                    "https://A.com/x?i=1",
                    "https://b.com/y",
                    "not-a-url",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return source

    def test_backend_creates_db(self, tmp_path: Path):
        source = self._source(tmp_path)
        out = tmp_path / "clean.txt"
        db = tmp_path / "uniq.db"
        code = main(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--backend",
                "sqlite",
                "--db",
                str(db),
            ]
        )
        assert code == 0
        conn = sqlite3.connect(db)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(urls)")]
        conn.close()
        assert set(columns) >= {
            "hash",
            "url",
            "normalized_url",
            "canonical_url",
            "first_seen",
            "duplicate_count",
            "category",
        }

    def test_resume_continues(self, tmp_path: Path):
        source = self._source(tmp_path)
        out = tmp_path / "clean.txt"
        db = tmp_path / "uniq.db"
        main(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--backend",
                "sqlite",
                "--db",
                str(db),
            ]
        )
        first_rows = len(out.read_text(encoding="utf-8").splitlines())
        conn = sqlite3.connect(db)
        first_uniques = conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        conn.close()

        # Second run without --resume recreates the DB.
        main(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--backend",
                "sqlite",
                "--db",
                str(db),
            ]
        )
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0] == first_uniques
        conn.close()

        # With --resume the store is retained and duplicates keep counting.
        main(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--backend",
                "sqlite",
                "--db",
                str(db),
                "--resume",
            ]
        )
        conn = sqlite3.connect(db)
        resumed_uniques = conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        dup_total = conn.execute("SELECT SUM(duplicate_count) FROM urls").fetchone()[0]
        conn.close()
        assert resumed_uniques == first_uniques
        assert dup_total > first_uniques
        assert first_rows == 3  # a.com/x?i=1, a.com/x?i=2, b.com/y/
