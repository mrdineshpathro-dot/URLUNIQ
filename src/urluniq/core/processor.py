"""High-level processing orchestration.

The :class:`Processor` wires together input parsing, the per-URL pipeline,
the deduplication engine, storage backends, optional multiprocessing,
streaming exporters, progress reporting, statistics, duplicate analysis,
grouping outputs and report generation.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from urluniq.classifiers.classifier import URLClassifier
from urluniq.config.loader import Config
from urluniq.core.pipeline import PipelineOptions, URLPipeline
from urluniq.dedupe.engine import DedupeEngine
from urluniq.dedupe.strategies import StrategyContext
from urluniq.exceptions import OutputError
from urluniq.exporters import CSVExporter, JSONExporter, JSONLExporter, TXTExporter, build_exporter
from urluniq.models import Backend, Features, URLRecord
from urluniq.parsers import detect_format, discover_files, iter_input
from urluniq.reports import csv_report, html_report, json_report
from urluniq.reports.statistics import ProcessingStats, RunResult, render_dashboard
from urluniq.storage.memory import MemoryStore
from urluniq.storage.sqlite import SQLiteStore

logger = logging.getLogger("urluniq")

# Multiprocessing worker state (per-process, set by the initializer).
_WORKER: dict[str, Any] = {}


def _init_worker(config: Config, profile: str, options: PipelineOptions) -> None:
    _WORKER["pipeline"] = URLPipeline(config, profile=profile, options=options)


def _process_chunk(lines: list[str]) -> list[URLRecord]:
    pipeline: URLPipeline = _WORKER["pipeline"]
    return [pipeline.process(line) for line in lines]


class ProgressReporter:
    """Minimal stderr progress line (disabled when piped or --quiet)."""

    def __init__(self, enabled: bool, interval: int) -> None:
        self.enabled = enabled and sys.stderr.isatty()
        self.interval = max(1, interval)
        self._next = self.interval

    def update(self, stats: ProcessingStats) -> None:
        if not self.enabled:
            return
        if stats.input_urls < self._next:
            return
        self._next = stats.input_urls + self.interval
        sys.stderr.write(
            f"\rProcessed: {stats.input_urls:,} | "
            f"Unique: {stats.unique_urls:,} | "
            f"Duplicates: {stats.duplicates:,} | "
            f"Invalid: {stats.invalid_urls:,}"
        )
        sys.stderr.flush()

    def finish(self, stats: ProcessingStats) -> None:
        if not self.enabled:
            return
        sys.stderr.write(
            f"\rProcessed: {stats.input_urls:,} | "
            f"Unique: {stats.unique_urls:,} | "
            f"Duplicates: {stats.duplicates:,} | "
            f"Invalid: {stats.invalid_urls:,} | "
            f"Speed: {stats.speed:,.0f} URLs/sec\n"
        )
        sys.stderr.flush()


@dataclass
class ProcessorOptions:
    """Runtime options from the CLI (already merged over the config)."""

    inputs: list[Path] = field(default_factory=list)
    input_dir: Path | None = None
    recursive: bool = False
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    input_format: str | None = None
    url_column: str | int | None = None
    json_field: str | None = None
    output: Path | None = None
    output_format: str | None = None
    invalid_output: Path | None = None
    duplicates_output: Path | None = None
    features_output: Path | None = None
    report: Path | None = None
    group_endpoint: Path | None = None
    group_host: Path | None = None
    group_domain: Path | None = None
    group_subdomain: Path | None = None
    group_path: Path | None = None
    use_stdin: bool = False
    explain: bool = False
    extract_features: bool = False
    classify: bool = True
    redact_userinfo: bool = False
    stats: bool = False
    sort: str = "none"
    emit_urls: bool = True
    classifier_rules: list = field(default_factory=list)


class _NullExporter:
    """Swallows records (used by ``analyze`` which emits no URL stream)."""

    def write(self, record: URLRecord) -> None:
        """Discard one record."""

    def finish(self) -> None:
        """Finalize the output."""


class _FeaturesWriter:
    """Writes extracted features as JSONL or CSV depending on extension."""

    def __init__(self, handle: TextIO, path: Path) -> None:
        self.handle = handle
        self._csv = None
        if path.suffix.lower() == ".csv":
            import csv

            fieldnames = list(
                Features(
                    url="",
                    normalized_url="",
                    canonical_url="",
                    scheme="",
                    host="",
                    subdomain="",
                    registrable_domain="",
                    port=0,
                    path="",
                    directory="",
                    filename="",
                    extension="",
                    query_param_count=0,
                    query_param_names=[],
                    has_fragment=False,
                    url_length=0,
                    path_depth=0,
                    category="",
                ).to_dict()
            )
            self._csv = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            self._csv.writeheader()

    def write(self, features: dict) -> None:
        if self._csv is not None:
            row = dict(features)
            row["query_param_names"] = " ".join(features.get("query_param_names", []))
            self._csv.writerow(row)
        else:
            self.handle.write(json.dumps(features, ensure_ascii=False) + "\n")


class Processor:
    """One processing run."""

    _last_duplicate_payload: list[dict[str, Any]] = field(default_factory=list)

    def __init__(self, config: Config, options: ProcessorOptions) -> None:
        self.config = config
        self.options = options
        # CLI --sort overrides [output] sort from the configuration.
        self.sort_mode = options.sort if options.sort != "none" else config.output.sort
        self.stats = ProcessingStats()
        if options.classifier_rules:
            classifier = URLClassifier(config.extension_map(), extra_rules=options.classifier_rules)
        else:
            classifier = None
        self.pipeline = URLPipeline(
            config,
            options=PipelineOptions(
                classify=options.classify,
                extract_features=options.extract_features,
                redact_userinfo=options.redact_userinfo,
            ),
            classifier=classifier,
        )

    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        """Execute the full run and return its result."""
        started = time.perf_counter()
        files = self._resolve_inputs()
        store = self._build_store()
        engine = DedupeEngine(
            store=store,
            mode=self.config.dedupe.mode,
            hash_algorithm=self.config.dedupe.hash_algorithm,
            use_hash_keys=self.config.dedupe.use_hash_keys,
            context=StrategyContext.from_config(self.config),
            collect_duplicates=self.options.duplicates_output is not None
            or self.options.report is not None,
            max_groups=self.config.output.duplicates_max_groups,
            max_variants=self.config.output.duplicates_max_variants,
        )

        accepted: list[URLRecord] = []  # used only when sorting is requested
        sort_needed = self.sort_mode != "none" or self._groups_requested()
        groups: dict[str, dict[str, list[str]]] = (
            {"endpoint": {}, "host": {}, "domain": {}, "subdomain": {}, "path": {}}
            if self._groups_requested()
            else {}
        )

        progress = ProgressReporter(
            enabled=True, interval=self.config.performance.progress_interval
        )
        invalid_handle = self._open_optional(self.options.invalid_output)
        features_handle = self._open_optional(self.options.features_output)
        features_writer: _FeaturesWriter | None = (
            _FeaturesWriter(features_handle, self.options.features_output)
            if features_handle is not None and self.options.features_output is not None
            else None
        )

        out_handle, close_out = (
            self._open_output() if self.options.emit_urls else (sys.stdout, False)
        )
        exporter: TXTExporter | CSVExporter | JSONExporter | JSONLExporter | _NullExporter
        try:
            if not self.options.emit_urls:
                exporter = _NullExporter()
            else:
                exporter = build_exporter(
                    self._output_format(),
                    out_handle,
                    csv_header=self.config.output.csv_header,
                    explain=self.options.explain,
                )
            workers = self._effective_workers(files)
            if workers > 1:
                self._run_parallel(
                    files,
                    engine,
                    exporter,
                    progress,
                    invalid_handle,
                    features_writer,
                    accepted,
                    sort_needed,
                    groups,
                    workers,
                )
            else:
                self._run_inline(
                    files,
                    engine,
                    exporter,
                    progress,
                    invalid_handle,
                    features_writer,
                    accepted,
                    sort_needed,
                    groups,
                )

            if sort_needed:
                self._write_sorted(accepted, engine, exporter)
            exporter.finish()
        finally:
            if close_out:
                out_handle.close()
            if invalid_handle is not None:
                invalid_handle.close()
            if features_handle is not None:
                features_handle.close()

        engine.commit_store()
        self.stats.elapsed_seconds = time.perf_counter() - started

        if self._groups_requested():
            self._write_groups(groups)

        self._last_duplicate_payload = self._duplicate_payload(engine)
        result = RunResult(stats=self.stats)
        result.duplicate_groups = self._last_duplicate_payload
        result.metadata = RunResult.build_metadata(
            config_dict=self.config.to_dict(),
            argv=sys.argv,
            input_names=[str(f) for f in files] or ["<stdin>"],
            output_name=str(self.options.output) if self.options.output else "<stdout>",
            profile=self.config.profile.value,
            dedupe_mode=self.config.dedupe.mode.value,
            backend=self.config.performance.backend,
            workers=self._effective_workers(files),
        )
        self._write_duplicates()
        self._write_report(result)
        logger.info("processing finished: %s", json.dumps(self.stats.to_dict()["input_urls"]))
        return result

    # -- input handling ---------------------------------------------------

    def _resolve_inputs(self) -> list[Path]:
        files = discover_files(
            paths=self.options.inputs,
            input_dir=self.options.input_dir,
            recursive=self.options.recursive,
            include=self.options.include_patterns or None,
            exclude=self.options.exclude_patterns or None,
        )
        for path in files:
            logger.info("input file: %s", path)
        return files

    def _iter_lines(self, files: list[Path]) -> Iterator[str]:
        if not files:
            if self.options.use_stdin:
                yield from iter_input(None, "txt")
            return
        for path in files:
            fmt = self.options.input_format or detect_format(path)
            yield from iter_input(path, fmt, self.options.url_column, self.options.json_field)

    def _chunks(self, lines: Iterator[str], size: int) -> Iterator[list[str]]:
        chunk: list[str] = []
        for line in lines:
            chunk.append(line)
            if len(chunk) >= size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    # -- run loops ----------------------------------------------------------

    def _run_inline(
        self,
        files: list[Path],
        engine: DedupeEngine,
        exporter: Any,
        progress: ProgressReporter,
        invalid_handle: TextIO | None,
        features_writer: _FeaturesWriter | None,
        accepted: list[URLRecord],
        sort_needed: bool,
        groups: dict[str, dict[str, list[str]]],
    ) -> None:
        pipeline = self.pipeline
        for raw in self._iter_lines(files):
            record = pipeline.process(raw)
            self._handle(
                record,
                engine,
                exporter,
                invalid_handle,
                features_writer,
                accepted,
                sort_needed,
                groups,
            )
            progress.update(self.stats)

    def _run_parallel(
        self,
        files: list[Path],
        engine: DedupeEngine,
        exporter: Any,
        progress: ProgressReporter,
        invalid_handle: TextIO | None,
        features_writer: _FeaturesWriter | None,
        accepted: list[URLRecord],
        sort_needed: bool,
        groups: dict[str, dict[str, list[str]]],
        workers: int,
    ) -> None:
        chunk_size = self.config.performance.chunk_size
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(self.config, self.config.profile.value, self.pipeline.options),
        ) as pool:
            for chunk in self._chunks(self._iter_lines(files), chunk_size):
                for records in pool.map(_process_chunk, [chunk]):
                    for record in records:
                        self._handle(
                            record,
                            engine,
                            exporter,
                            invalid_handle,
                            features_writer,
                            accepted,
                            sort_needed,
                            groups,
                        )
                    progress.update(self.stats)

    def _handle(
        self,
        record: URLRecord,
        engine: DedupeEngine,
        exporter: Any,
        invalid_handle: TextIO | None,
        features_writer: _FeaturesWriter | None,
        accepted: list[URLRecord],
        sort_needed: bool,
        groups: dict[str, dict[str, list[str]]],
    ) -> None:
        self.stats.input_urls += 1
        if record.error:
            self.stats.observe_invalid(record.raw, record.error)
            if invalid_handle is not None:
                invalid_handle.write(f"{record.raw}\t{record.error}\n")
            return
        self.stats.observe_valid(record)
        if record.dropped:
            self.stats.filtered_out += 1
            return
        if sort_needed:
            accepted.append(record)
        first = engine.add(record)
        if first:
            self.stats.unique_urls += 1
            if record.features is not None and features_writer is not None:
                features_writer.write(record.features)
            if not sort_needed:
                exporter.write(record)
        else:
            self.stats.duplicates += 1
        if groups:
            self._group(groups, record)

    # -- outputs ----------------------------------------------------------

    def _write_sorted(self, accepted: list[URLRecord], engine: DedupeEngine, exporter: Any) -> None:
        mode = self.sort_mode
        unique = [r for r in accepted if not r.dropped]
        if mode == "url":
            unique.sort(key=lambda r: (r.normalized, r.raw))
        elif mode == "host":
            unique.sort(key=lambda r: (r.host, r.normalized))
        elif mode == "category":
            unique.sort(key=lambda r: (r.category, r.host, r.normalized))
        seen: set[str] = set()
        for record in unique:
            key = engine.key_for(record)
            if key in seen:
                continue
            seen.add(key)
            exporter.write(record)

    def _group(self, groups: dict[str, dict[str, list[str]]], record: URLRecord) -> None:
        cap = self.config.output.duplicates_max_variants
        url = record.normalized or record.raw
        buckets = {
            "endpoint": f"{record.host}{record.path}",
            "host": record.host,
            "domain": record.registrable_domain,
            "subdomain": record.subdomain or "(root)",
            "path": record.path or "/",
        }
        for name, key in buckets.items():
            table = groups.get(name)
            if table is None:
                continue
            variants = table.setdefault(key, [])
            if len(variants) < cap and url not in variants:
                variants.append(url)

    def _groups_requested(self) -> bool:
        opts = self.options
        return any(
            path is not None
            for path in (
                opts.group_endpoint,
                opts.group_host,
                opts.group_domain,
                opts.group_subdomain,
                opts.group_path,
            )
        )

    def _write_groups(self, groups: dict[str, dict[str, list[str]]]) -> None:
        targets = {
            "endpoint": self.options.group_endpoint,
            "host": self.options.group_host,
            "domain": self.options.group_domain,
            "subdomain": self.options.group_subdomain,
            "path": self.options.group_path,
        }
        for name, path in targets.items():
            if path is None:
                continue
            self._write_group_file(name, path, groups.get(name, {}))

    def _write_group_file(self, name: str, path: Path, table: dict[str, list[str]]) -> None:
        try:
            with path.open("w", encoding="utf-8") as handle:
                handle.write(f"# URLUNIQ {name} groups ({len(table)} groups)\n")
                for key in sorted(table, key=lambda k: (-len(table[k]), k)):
                    variants = table[key]
                    handle.write(
                        f"\n[{key}] ({len(variants)} URL{'s' if len(variants) != 1 else ''})\n"
                    )
                    for url in variants:
                        handle.write(f"  {url}\n")
        except OSError as exc:
            raise OutputError(f"cannot write group output {path}: {exc}") from exc

    def _open_optional(self, path: Path | None) -> TextIO | None:
        if path is None:
            return None
        try:
            return path.open("w", encoding="utf-8")
        except OSError as exc:
            raise OutputError(f"cannot open output {path}: {exc}") from exc

    def _open_output(self) -> tuple[TextIO, bool]:
        if self.options.output is None:
            return sys.stdout, False
        path = self.options.output
        if path.exists() and path.stat().st_size > 0:
            # Protect existing report files from accidental overwrite.
            suffix = path.suffix.lower()
            if suffix in (".html", ".htm"):
                backup = path.with_suffix(path.suffix + ".bak")
                logger.warning("existing report %s kept as %s", path, backup)
                path.rename(backup)
        try:
            handle = path.open("w", encoding="utf-8")
        except OSError as exc:
            raise OutputError(f"cannot open output file {path}: {exc}") from exc
        return handle, True

    def _output_format(self) -> str:
        if self.options.output_format:
            return self.options.output_format
        if self.options.output is not None and self.options.output.suffix:
            ext = self.options.output.suffix.lower().lstrip(".")
            if ext in {"txt", "csv", "json", "jsonl"}:
                return ext
        return self.config.output.format

    def _effective_workers(self, files: list[Path]) -> int:
        workers = max(1, self.config.performance.workers)
        if workers > 1:
            total = sum(f.stat().st_size for f in files) if files else 0
            if total < self.config.performance.multiprocess_min_lines * 8:
                # Small inputs: multiprocessing would only add overhead.
                logger.debug("workers=%d ignored for small input (%d bytes)", workers, total)
                return 1
        return workers

    def _build_store(self) -> MemoryStore | SQLiteStore:
        backend = Backend(self.config.performance.backend)
        if backend is Backend.SQLITE:
            return SQLiteStore(
                self.config.performance.sqlite_path,
                resume=self.config.performance.resume,
            )
        return MemoryStore()

    def _duplicate_payload(self, engine: DedupeEngine) -> list[dict[str, Any]]:
        return [
            {
                "canonical": group.canonical,
                "variants": group.variants,
                "count": group.count,
            }
            for group in engine.duplicate_groups
            if group.count > 1
        ]

    def _write_duplicates(self) -> None:
        path = self.options.duplicates_output
        if path is None:
            return
        payload = self._last_duplicate_payload
        try:
            if path.suffix.lower() == ".json":
                path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
            else:
                with path.open("w", encoding="utf-8") as handle:
                    for group in payload:
                        handle.write("CANONICAL:\n")
                        handle.write(f"{group['canonical']}\n\nVARIANTS:\n")
                        for variant in group["variants"]:
                            handle.write(f"{variant}\n")
                        handle.write(f"\nCOUNT:\n{group['count']}\n")
                        handle.write("=" * 48 + "\n")
        except OSError as exc:
            raise OutputError(f"cannot write duplicates output {path}: {exc}") from exc

    def _write_report(self, result: RunResult) -> None:
        path = self.options.report
        if path is None:
            return
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                json_report.write(path, result)
            elif suffix == ".csv":
                csv_report.write(path, result)
            elif suffix in (".html", ".htm"):
                html_report.write(path, result)
            else:
                raise OutputError(f"unsupported report format '{suffix}' (use .json/.csv/.html)")
        except OSError as exc:
            raise OutputError(f"cannot write report {path}: {exc}") from exc
        logger.info("report written: %s", path)

    def print_dashboard(self, stream: TextIO | None = None) -> None:
        target = stream or sys.stderr
        target.write(render_dashboard(self.stats) + "\n")
