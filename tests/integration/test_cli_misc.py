"""Integration tests for analyze / diff / inspect / config / version."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import FakeStdin, FakeTty
from urluniq.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


class TestAnalyze:
    def test_dashboard_and_tops(self, urls_file: Path, capsys):
        code = main(["analyze", "-i", str(urls_file)])
        assert code == 0
        captured = capsys.readouterr()
        assert "URLUNIQ 2.0 REPORT" in captured.out
        assert "Top hosts" in captured.out
        assert "Top parameters" in captured.out
        assert "Category" in captured.out

    def test_analyze_no_url_stream_on_stdout(self, urls_file: Path, capsys):
        main(["analyze", "-i", str(urls_file), "--quiet"])
        captured = capsys.readouterr()
        # The dashboard is data, not a URL per line - only 4 unique URLs exist.
        assert "https://example.com/search/?q=1&utm_source=test" not in captured.out

    def test_analyze_report(self, urls_file: Path, tmp_path: Path):
        report = tmp_path / "report.json"
        main(["analyze", "-i", str(urls_file), "--quiet", "--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["summary"]["input_urls"] == 8
        assert payload["metadata"]["urluniq_version"]


class TestDiff:
    def test_diff_summary(self, capsys):
        code = main(
            [
                "diff",
                str(EXAMPLES / "old_urls.txt"),
                str(EXAMPLES / "new_urls.txt"),
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "New:" in captured.out
        assert "Removed:" in captured.out
        assert "Unchanged:" in captured.out
        assert "Changed:" in captured.out

    def test_diff_exports(self, tmp_path: Path):
        json_path = tmp_path / "d.json"
        csv_path = tmp_path / "d.csv"
        txt_path = tmp_path / "d.txt"
        code = main(
            [
                "diff",
                str(EXAMPLES / "old_urls.txt"),
                str(EXAMPLES / "new_urls.txt"),
                "--quiet",
                "--diff-json",
                str(json_path),
                "--diff-csv",
                str(csv_path),
                "--diff-txt",
                str(txt_path),
            ]
        )
        assert code == 0
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["summary"]["new"] >= 1
        assert csv_path.read_text(encoding="utf-8").startswith("status,canonical")
        assert "NEW URLS" in txt_path.read_text(encoding="utf-8")

    def test_diff_missing_input_exit_code(self, tmp_path: Path):
        code = main(["diff", str(tmp_path / "nope.txt"), str(tmp_path / "nope2.txt")])
        assert code == 3


class TestInspect:
    def test_inspect_output(self, capsys):
        code = main(["inspect", "https://example.com/search?q=test&utm_source=x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "URLUNIQ INSPECT" in captured.out
        assert "Normalized URL    : https://example.com/search/" in captured.out
        assert "Canonical URL     : https://example.com/search/?q=test" in captured.out
        assert "Classification    : Search" in captured.out
        assert "Applied transformations:" in captured.out
        assert "trailing slash added" in captured.out

    def test_inspect_redacts_credentials(self, capsys):
        main(["inspect", "https://admin:supersecret@example.com/admin"])
        captured = capsys.readouterr()
        assert "supersecret" not in captured.out
        assert "[REDACTED]" in captured.out

    def test_inspect_show_userinfo(self, capsys):
        main(["inspect", "https://admin:pw@example.com/admin", "--show-userinfo"])
        captured = capsys.readouterr()
        assert "admin:pw@example.com" in captured.out

    def test_inspect_invalid(self, capsys):
        code = main(["inspect", "not a url at all"])
        assert code == 0
        assert "INVALID" in capsys.readouterr().out

    def test_inspect_profile(self, capsys):
        main(["inspect", "https://example.com/x?a=2&b=1#f", "--profile", "safe"])
        captured = capsys.readouterr()
        assert "#f" in captured.out  # safe profile keeps the fragment


class TestConfigCommand:
    def test_config_dump(self, capsys):
        code = main(["config"])
        assert code == 0
        captured = capsys.readouterr()
        assert "effective configuration" in captured.out
        assert "[normalization]" in captured.out
        assert "Tracking parameters configured:" in captured.out

    def test_config_json(self, capsys):
        code = main(["config", "--json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["profile"] == "standard"

    def test_config_custom_file(self, tmp_path: Path, capsys):
        custom = tmp_path / "c.toml"
        custom.write_text('profile = "aggressive"\n', encoding="utf-8")
        code = main(["config", "--config", str(custom), "--json"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["profile"] == "aggressive"

    def test_config_bad_file_exit_code(self, tmp_path: Path):
        code = main(["config", "--config", str(tmp_path / "missing.toml")])
        assert code == 5


class TestVersion:
    def test_version(self, capsys):
        assert main(["version"]) == 0
        captured = capsys.readouterr()
        assert "URLUNIQ 2.0 (2.0.0)" in captured.out
        assert "mrdineshpathro-dot" in captured.out
        assert "https://www.youtube.com/@GithubHacker" in captured.out

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert "URLUNIQ 2.0.0" in capsys.readouterr().out


class TestExitCodes:
    def test_no_input_with_tty_is_usage_error(self, monkeypatch):
        import sys

        class TtyStdin:
            def isatty(self):
                return True

        monkeypatch.setattr(sys, "stdin", TtyStdin())
        assert main(["clean"]) == 2

    def test_missing_input_file(self, tmp_path: Path):
        assert main(["clean", "-i", str(tmp_path / "gone.txt"), "--quiet"]) == 3

    def test_bad_report_extension_is_output_error(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "o.txt"
        report = tmp_path / "r.xyz"
        assert (
            main(
                ["clean", "-i", str(urls_file), "-o", str(out), "--quiet", "--report", str(report)]
            )
            == 4
        )

    def test_bad_config_is_config_error(self, tmp_path: Path):
        assert main(["clean", "--config", str(tmp_path / "none.toml"), "--quiet"]) == 5

    def test_success(self, urls_file: Path, tmp_path: Path):
        out = tmp_path / "o.txt"
        assert main(["clean", "-i", str(urls_file), "-o", str(out), "--quiet"]) == 0

    def test_no_subcommand_shows_help(self, monkeypatch, capsys):
        import sys

        monkeypatch.setattr(sys, "stdin", FakeTty(""))
        assert main([]) == 2
        assert "usage" in capsys.readouterr().out.lower()

    def test_bare_urluniq_with_stdin_defaults_to_clean(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", FakeStdin("https://a.com/\nhttps://a.com\n"))
        assert main([]) == 0
        assert capsys.readouterr().out == "https://a.com/\n"

    def test_unknown_flag_with_no_subcommand_is_usage_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--nonsense"])
        assert exc.value.code == 2
