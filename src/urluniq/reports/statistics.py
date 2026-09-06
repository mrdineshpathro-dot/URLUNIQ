"""Statistics collection, dashboards and Top-N reports."""

from __future__ import annotations

import platform
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from urluniq import __version__
from urluniq.constants import APP_TITLE
from urluniq.models import URLRecord


@dataclass
class ProcessingStats:
    """Counters maintained for one processing run."""

    input_urls: int = 0
    valid_urls: int = 0
    invalid_urls: int = 0
    duplicates: int = 0
    unique_urls: int = 0
    filtered_out: int = 0
    normalization_changes: int = 0
    canonical_changes: int = 0
    tracking_removed_urls: int = 0
    tracking_params_removed: int = 0
    parameterized_urls: int = 0
    elapsed_seconds: float = 0.0

    errors: Counter[str] = field(default_factory=Counter)
    hosts: Counter[str] = field(default_factory=Counter)
    domains: Counter[str] = field(default_factory=Counter)
    subdomains: Counter[str] = field(default_factory=Counter)
    paths: Counter[str] = field(default_factory=Counter)
    extensions: Counter[str] = field(default_factory=Counter)
    params: Counter[str] = field(default_factory=Counter)
    categories: Counter[str] = field(default_factory=Counter)

    total_length: int = 0
    max_length: int = 0
    min_length: int = 0
    largest_urls: list[tuple[int, str]] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)

    MAX_EXAMPLES = 25
    MAX_LARGEST = 5

    # ------------------------------------------------------------------

    def observe_invalid(self, raw: str, reason: str) -> None:
        self.invalid_urls += 1
        self.errors[reason.split(":")[0]] += 1
        _ = raw

    def observe_valid(self, record: URLRecord) -> None:
        self.valid_urls += 1
        if record.raw != record.normalized:
            self.normalization_changes += 1
        if record.normalized != record.canonical:
            self.canonical_changes += 1
        if record.tracking_removed:
            self.tracking_removed_urls += 1
            self.tracking_params_removed += record.tracking_removed
        if record.param_count > 0:
            self.parameterized_urls += 1

        self.hosts[record.host] += 1
        self.domains[record.registrable_domain] += 1
        if record.subdomain:
            self.subdomains[record.subdomain] += 1
        self.paths[record.path or "/"] += 1
        if record.extension:
            self.extensions[record.extension] += 1
        for name in record.param_names:
            self.params[name] += 1
        self.categories[record.category] += 1

        length = record.url_length
        self.total_length += length
        if length > self.max_length:
            self.max_length = length
        if self.min_length == 0 or length < self.min_length:
            self.min_length = length
        self._track_largest(length, record.raw)
        if record.raw != record.normalized and len(self.examples) < self.MAX_EXAMPLES:
            self.examples.append(
                {
                    "original": record.raw,
                    "normalized": record.normalized,
                    "changes": record.reasons,
                }
            )

    def _track_largest(self, length: int, url: str) -> None:
        self.largest_urls.append((length, url))
        self.largest_urls.sort(key=lambda item: (-item[0], item[1]))
        del self.largest_urls[self.MAX_LARGEST :]

    @property
    def average_length(self) -> float:
        return self.total_length / self.valid_urls if self.valid_urls else 0.0

    @property
    def speed(self) -> float:
        return self.input_urls / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_urls": self.input_urls,
            "valid_urls": self.valid_urls,
            "invalid_urls": self.invalid_urls,
            "duplicates": self.duplicates,
            "unique_urls": self.unique_urls,
            "filtered_out": self.filtered_out,
            "normalization_changes": self.normalization_changes,
            "canonical_changes": self.canonical_changes,
            "tracking_removed_urls": self.tracking_removed_urls,
            "tracking_params_removed": self.tracking_params_removed,
            "parameterized_urls": self.parameterized_urls,
            "average_url_length": round(self.average_length, 2),
            "max_url_length": self.max_length,
            "min_url_length": self.min_length,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "urls_per_second": round(self.speed),
            "errors": dict(self.errors),
            "top_hosts": self.hosts.most_common(10),
            "top_domains": self.domains.most_common(10),
            "top_subdomains": self.subdomains.most_common(10),
            "top_paths": self.paths.most_common(10),
            "top_extensions": self.extensions.most_common(10),
            "top_parameters": self.params.most_common(10),
            "categories": dict(self.categories),
            "largest_urls": [{"length": n, "url": u} for n, u in self.largest_urls],
            "example_transformations": self.examples,
        }


@dataclass
class RunResult:
    """Everything needed by reports for one completed run."""

    stats: ProcessingStats = field(default_factory=ProcessingStats)
    metadata: dict[str, Any] = field(default_factory=dict)
    duplicate_groups: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.stats.to_dict(),
            "duplicates": self.duplicate_groups,
            "metadata": self.metadata,
        }

    @staticmethod
    def build_metadata(
        *,
        config_dict: dict[str, Any],
        argv: list[str],
        input_names: list[str],
        output_name: str,
        profile: str,
        dedupe_mode: str,
        backend: str,
        workers: int,
    ) -> dict[str, Any]:
        """Reproducibility block recorded in every report."""
        return {
            "urluniq_version": __version__,
            "python_version": sys.version.split()[0],
            "operating_system": (
                f"{platform.system()} {platform.release()}" if platform else "unknown"
            ),
            "profile": profile,
            "dedupe_mode": dedupe_mode,
            "backend": backend,
            "workers": workers,
            "configuration": config_dict,
            "command_line": argv,
            "processing_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_files": input_names,
            "output_file": output_name,
        }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

DASH_WIDTH = 48


def render_dashboard(stats: ProcessingStats) -> str:
    """The end-of-run statistics dashboard (section 25 layout)."""
    line = "=" * DASH_WIDTH
    rows = [
        ("Input URLs", f"{stats.input_urls:,}"),
        ("Valid URLs", f"{stats.valid_urls:,}"),
        ("Invalid URLs", f"{stats.invalid_urls:,}"),
        ("Filtered URLs", f"{stats.filtered_out:,}"),
        ("Duplicates", f"{stats.duplicates:,}"),
        ("Unique URLs", f"{stats.unique_urls:,}"),
        ("Canonical changes", f"{stats.canonical_changes:,}"),
        ("Tracking removed", f"{stats.tracking_removed_urls:,}"),
        ("Parameterized URLs", f"{stats.parameterized_urls:,}"),
    ]
    footer = [
        ("Processing time", f"{stats.elapsed_seconds:.2f} sec"),
        ("Processing speed", f"{stats.speed:,.0f} URLs/sec"),
    ]
    out = [line, f"{APP_TITLE} REPORT", line]
    out += [f"{label:<20}: {value}" for label, value in rows]
    out.append("")
    out += [f"{label:<20}: {value}" for label, value in footer]
    out.append(line)
    return "\n".join(out)


def render_classification_summary(stats: ProcessingStats) -> str:
    """Category table shown by ``analyze`` and ``--classify``."""
    if not stats.categories:
        return "No classified URLs."
    width = max(len(label) for label in stats.categories)
    lines = [f"{label:<{width + 2}}{count:>8}" for label, count in stats.categories.most_common()]
    header = f"{'Category':<{width + 2}}{'Count':>8}"
    return "\n".join([header, "-" * (width + 10)] + lines)


def render_top(label: str, counter: Counter[str], limit: int = 10) -> str:
    """A Top-N block for hosts/paths/extensions/parameters."""
    if not counter:
        return f"Top {label}: (none)"
    width = max(len(str(k)) for k, _ in counter.most_common(limit)) + 2
    lines = [f"Top {label}", "-" * min(DASH_WIDTH, width + 10)]
    lines += [f"{key:<{width}}{count:>8,}" for key, count in counter.most_common(limit)]
    return "\n".join(lines)
