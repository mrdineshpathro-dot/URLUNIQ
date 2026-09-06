"""URLUNIQ 2.0 benchmark suite.

Generates synthetic URL datasets, processes them through the URLUNIQ
pipeline and measures runtime, memory and throughput.

Usage::

    python benchmarks/run_benchmark.py                 # 10K + 100K (quick)
    python benchmarks/run_benchmark.py --sizes 1000000
    python benchmarks/run_benchmark.py --sizes 10000 100000 1000000 5000000
    python benchmarks/run_benchmark.py --json out.json

The benchmark writes its dataset to a temporary file and processes it with
the real CLI code path (streaming, memory backend) so numbers reflect the
tool, not a stripped-down loop.
"""

from __future__ import annotations

import argparse
import json
import random
import resource
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urluniq import __version__  # noqa: E402
from urluniq.config.loader import Config  # noqa: E402
from urluniq.core.processor import Processor, ProcessorOptions  # noqa: E402
from urluniq.models import DedupeMode  # noqa: E402

HOSTS = [
    "www.example.com",
    "api.example.com",
    "admin.example.com",
    "shop.example.com",
    "docs.example.org",
    "cdn.example.net",
    "portal.example.io",
    "old.example.co.uk",
]
PATHS = [
    "/",
    "/search",
    "/login",
    "/logout",
    "/api/v1/users",
    "/api/v1/orders",
    "/static/app.js",
    "/static/style.css",
    "/images/logo.png",
    "/a/b/c/d/e",
    "/admin/dashboard",
    "/reports/2026/q3.pdf",
    "/upload",
    "/settings/profile",
]
PARAMS = [
    "",
    "?q=1",
    "?q=2",
    "?page=1&size=20",
    "?page=2&size=20",
    "?utm_source=x&utm_medium=y&q=1",
    "?id=1",
    "?id=2&sort=desc",
    "?session=abc123&q=1",
    "?ref=footer",
]


def generate_dataset(path: Path, count: int, seed: int = 1337) -> None:
    """Write ``count`` synthetic URLs to ``path`` with realistic noise."""
    rng = random.Random(seed)
    hosts, paths, params = HOSTS, PATHS, PARAMS
    write = path.open("w", encoding="utf-8")
    try:
        for _ in range(count):
            scheme = "https"
            roll = rng.random()
            if roll < 0.15:
                scheme = "HTTPS"
            elif roll < 0.25:
                scheme = "http"
            host = rng.choice(hosts)
            if rng.random() < 0.10:
                host = host.upper()
            url_path = rng.choice(paths)
            suffix = rng.choice(params)
            if rng.random() < 0.05:
                suffix += "#fragment"
            write.write(f"{scheme}://{host}{url_path}{suffix}\n")
    finally:
        write.close()


@dataclass
class BenchmarkResult:
    size: int
    runtime_seconds: float
    urls_per_second: float
    peak_rss_mb: float
    unique_urls: int
    duplicates: int
    invalid: int


def run_benchmark(size: int, dedupe: str = "normalized") -> BenchmarkResult:
    """Benchmark one dataset size end-to-end through the Processor."""
    with tempfile.TemporaryDirectory(prefix="urluniq-bench-") as tmp:
        dataset = Path(tmp) / "urls.txt"
        generate_dataset(dataset, size)
        output = Path(tmp) / "clean.txt"

        config = Config()
        config.dedupe.mode = DedupeMode(dedupe)
        options = ProcessorOptions(inputs=[dataset], output=output)
        processor = Processor(config, options)

        start = time.perf_counter()
        result = processor.run()
        runtime = time.perf_counter() - start

        peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        stats = result.stats
        return BenchmarkResult(
            size=size,
            runtime_seconds=round(runtime, 3),
            urls_per_second=round(size / runtime) if runtime else 0,
            peak_rss_mb=round(peak_rss_kb / 1024, 1),
            unique_urls=stats.unique_urls,
            duplicates=stats.duplicates,
            invalid=stats.invalid_urls,
        )


def render_table(results: list[BenchmarkResult]) -> str:
    """Pretty-print benchmark results."""
    header = (
        f"{'URLs':>10} | {'runtime':>9} | {'urls/sec':>11} | {'peak RSS':>9}"
        f" | {'unique':>8} | {'dups':>8} | {'invalid':>8}"
    )
    lines = [
        "=" * len(header),
        f"URLUNIQ {__version__} benchmark",
        "=" * len(header),
        header,
        "-" * len(header),
    ]
    for r in results:
        lines.append(
            f"{r.size:>10,} | {r.runtime_seconds:>7.2f}s | {r.urls_per_second:>11,} | "
            f"{r.peak_rss_mb:>7.1f}MB | {r.unique_urls:>8,} | {r.duplicates:>8,} | {r.invalid:>8,}"
        )
    lines.append("=" * len(header))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="URLUNIQ benchmark suite")
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=None,
        help="dataset sizes (default: --quick -> 10K and 100K)",
    )
    parser.add_argument("--quick", action="store_true", help="10K + 100K sizes")
    parser.add_argument(
        "--full", action="store_true", help="10K, 100K, 1M and 5M sizes (needs RAM + time)"
    )
    parser.add_argument(
        "--dedupe",
        default="normalized",
        choices=[
            "exact",
            "normalized",
            "canonical",
            "host",
            "path",
            "path_query",
            "smart",
        ],
    )
    parser.add_argument("--json", metavar="FILE", help="also write results as JSON")
    args = parser.parse_args(argv)

    if args.sizes:
        sizes = args.sizes
    elif args.full:
        sizes = [10_000, 100_000, 1_000_000, 5_000_000]
    else:
        sizes = [10_000, 100_000]

    print(f"URLUNIQ {__version__} benchmark | dedupe={args.dedupe} | sizes={sizes}")
    results: list[BenchmarkResult] = []
    for size in sizes:
        print(f"  generating {size:,} URLs ...", flush=True)
        results.append(run_benchmark(size, dedupe=args.dedupe))
        print(f"  done: {results[-1].urls_per_second:,} URLs/sec", flush=True)

    print()
    print(render_table(results))
    if args.json:
        Path(args.json).write_text(
            json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nresults written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
