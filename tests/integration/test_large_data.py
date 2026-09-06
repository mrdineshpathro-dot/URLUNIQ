"""Large-data processing tests (100K URLs) and the multiprocessing path."""

from __future__ import annotations

import random
from pathlib import Path

from urluniq.cli import main


def _generate(path: Path, count: int, seed: int = 42) -> None:
    rng = random.Random(seed)
    hosts = ["a.example.com", "b.example.com", "api.example.com", "other.net"]
    paths = ["/", "/search", "/api/v1/users", "/static/app.js", "/a/b/c", "/login"]
    params = ["", "?q=1", "?q=2", "?page=1&size=20", "?q=3", "?utm_source=x&q=3"]
    with path.open("w", encoding="utf-8") as handle:
        for i in range(count):
            host = rng.choice(hosts)
            url_path = rng.choice(paths)
            scheme = "https"
            if i % 1000 == 0:
                scheme = "HTTPS"  # casing noise that normalization collapses
            line = f"{scheme}://{host}{url_path}{rng.choice(params)}"
            handle.write(line + "\n")


class TestLargeData:
    def test_100k_memory_backend(self, tmp_path: Path):
        source = tmp_path / "big.txt"
        _generate(source, 100_000)
        out = tmp_path / "clean.txt"
        code = main(["clean", "-i", str(source), "-o", str(out), "--quiet"])
        assert code == 0
        # Deterministic dataset: 4 hosts x 6 paths x 6 param sets = 144 uniques.
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 144
        assert len(set(lines)) == 144

    def test_100k_with_workers(self, tmp_path: Path):
        source = tmp_path / "big.txt"
        _generate(source, 100_000, seed=7)
        out = tmp_path / "clean.txt"
        code = main(
            [
                "clean",
                "-i",
                str(source),
                "-o",
                str(out),
                "--quiet",
                "--workers",
                "2",
                "--dedupe",
                "normalized",
            ]
        )
        assert code == 0
        lines = out.read_text(encoding="utf-8").splitlines()
        # Multiprocessing must produce the identical result as inline runs.
        assert len(lines) == 144
        assert len(set(lines)) == 144

    def test_100k_canonical_collapses_tracking(self, tmp_path: Path):
        source = tmp_path / "big.txt"
        _generate(source, 100_000, seed=11)
        out = tmp_path / "clean.txt"
        code = main(
            ["clean", "-i", str(source), "-o", str(out), "--quiet", "--dedupe", "canonical"]
        )
        assert code == 0
        lines = out.read_text(encoding="utf-8").splitlines()
        # Canonical identity drops tracking params: ?utm_source=x&q=3 merges
        # into ?q=3 -> 4 x 6 x 5 = 120 canonical uniques.
        assert len(lines) == 120

    def test_sqlite_backend_50k(self, tmp_path: Path):
        source = tmp_path / "big.txt"
        _generate(source, 50_000, seed=9)
        out = tmp_path / "clean.txt"
        db = tmp_path / "big.db"
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
        assert len(out.read_text(encoding="utf-8").splitlines()) == 144

    def test_progress_disabled_when_piped(self, urls_file: Path, capsys):
        # Not a tty -> no progress line on stderr even without --quiet.
        code = main(["clean", "-i", str(urls_file), "-o", "/dev/null"])
        assert code == 0
        assert "Processed:" not in capsys.readouterr().err
