"""URLUNIQ command-line interface.

Subcommands
-----------
``clean``     normalize + deduplicate a dataset (writes clean output)
``analyze``   statistics dashboard, classification and Top-N reports
``diff``      differential analysis between two datasets
``inspect``   deep inspection of a single URL (offline)
``config``    show the effective configuration
``version``   version and author information

Exit codes: 0 success, 1 general error, 2 invalid arguments, 3 input error,
4 output error, 5 configuration error.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import IO

from urluniq import __version__
from urluniq.config.loader import Config
from urluniq.constants import (
    APP_SUBTITLE,
    APP_TITLE,
    AUTHOR,
    BANNER,
    GITHUB_URL,
    PRIMARY_TAGLINE,
    SECONDARY_TAGLINE,
    YOUTUBE_URL,
    ExitCode,
)
from urluniq.core.diff import DiffResult, compute_diff, export_csv, export_json, export_txt
from urluniq.core.pipeline import URLPipeline
from urluniq.core.processor import Processor, ProcessorOptions
from urluniq.dedupe.hashing import fingerprint  # noqa: F401  (documented API)
from urluniq.dedupe.strategies import available_modes
from urluniq.exceptions import InputError, URLUNIQError
from urluniq.models import Backend, DedupeMode, HashAlgorithm, Profile
from urluniq.parsers import detect_format, iter_input
from urluniq.plugins import PluginRegistry, load_plugins
from urluniq.reports.statistics import (
    render_classification_summary,
    render_dashboard,
    render_top,
)

logger = logging.getLogger("urluniq")

_CREDENTIAL_RE = re.compile(r"://[^/@\s]+@")


def redact(text: str) -> str:
    """Redact URL credentials in log/console output unless explicitly shown."""
    return _CREDENTIAL_RE.sub("://[REDACTED]@", text)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", metavar="FILE", help="path to a TOML configuration file")
    parser.add_argument("--quiet", action="store_true", help="suppress banner, progress and stats")
    parser.add_argument("--verbose", action="store_true", help="verbose output on stderr")
    parser.add_argument("--debug", action="store_true", help="debug output on stderr")
    parser.add_argument("--log", metavar="FILE", help="write a structured log file")
    parser.add_argument(
        "--log-format", choices=("text", "json"), default="text", help="log file format"
    )


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-i",
        "--input",
        action="append",
        default=[],
        metavar="FILE",
        help="input file (repeatable; '-' for stdin)",
    )
    parser.add_argument("--input-dir", metavar="DIR", help="process every file in a directory")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="with --input-dir, descend into subdirectories",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help='file pattern to include, e.g. "*.txt" (repeatable)',
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help='file pattern to exclude, e.g. "*.bak" (repeatable)',
    )
    parser.add_argument(
        "--input-format",
        choices=("txt", "csv", "json", "jsonl"),
        help="force the input format (default: detect from extension)",
    )
    parser.add_argument("--url-column", metavar="COL", help="CSV URL column (name or index)")
    parser.add_argument(
        "--json-field", metavar="FIELD", help='JSON/JSONL URL field (default "url")'
    )


def _add_processing(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile", choices=[p.value for p in Profile], help="normalization profile"
    )
    parser.add_argument("--dedupe", choices=available_modes(), help="deduplication strategy")
    parser.add_argument(
        "--backend", choices=[b.value for b in Backend], help="deduplication storage backend"
    )
    parser.add_argument("--db", metavar="FILE", help="SQLite database path (--backend sqlite)")
    parser.add_argument("--resume", action="store_true", help="resume a previous SQLite run")
    parser.add_argument(
        "--workers", type=int, metavar="N", help="worker processes for large inputs"
    )
    parser.add_argument(
        "--hash",
        dest="hash_algo",
        choices=[h.value for h in HashAlgorithm],
        help="fingerprint algorithm for identity keys",
    )
    parser.add_argument("--remove-tracking", action="store_true", help="remove tracking parameters")
    parser.add_argument(
        "--keep-param",
        action="append",
        default=[],
        metavar="NAME",
        help="query parameter allowlist entry (repeatable)",
    )
    parser.add_argument(
        "--drop-param",
        action="append",
        default=[],
        metavar="NAME",
        help="query parameter denylist entry (repeatable)",
    )
    parser.add_argument("--classify", action="store_true", help="print the classification summary")
    parser.add_argument(
        "--explain", action="store_true", help="include transformation reasons in structured output"
    )


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", metavar="DOMAIN", help="restrict output to one domain")
    parser.add_argument(
        "--include-subdomains",
        action="store_true",
        help="with --domain, also accept subdomains",
    )
    for name in ("host", "extension", "path"):
        parser.add_argument(
            f"--include-{name}",
            action="append",
            default=[],
            metavar="VALUE",
            help=f"only keep URLs matching this {name} (repeatable)",
        )
        parser.add_argument(
            f"--exclude-{name}",
            action="append",
            default=[],
            metavar="VALUE",
            help=f"drop URLs matching this {name} (repeatable)",
        )
    parser.add_argument(
        "--include-regex",
        action="append",
        default=[],
        metavar="PATTERN",
        help="only keep URLs matching this regex (repeatable)",
    )
    parser.add_argument(
        "--exclude-regex",
        action="append",
        default=[],
        metavar="PATTERN",
        help="drop URLs matching this regex (repeatable)",
    )


def _add_groups(parser: argparse.ArgumentParser) -> None:
    for flag, dest in (
        ("--group-by-endpoint", "group_endpoint"),
        ("--group-host", "group_host"),
        ("--group-domain", "group_domain"),
        ("--group-subdomain", "group_subdomain"),
        ("--group-path", "group_path"),
    ):
        label = dest.replace("group_", "").replace("_", " ")
        default_file = f"{dest}.txt"
        parser.add_argument(
            flag,
            dest=dest,
            nargs="?",
            const=default_file,
            metavar="FILE",
            help=f"write {label} groups to FILE (default: {default_file})",
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="urluniq",
        description=f"{APP_TITLE} - {PRIMARY_TAGLINE} ({SECONDARY_TAGLINE})",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"URLUNIQ {__version__}",
        help="show version and exit",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # clean --------------------------------------------------------------
    clean = sub.add_parser(
        "clean",
        help="normalize and deduplicate URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common(clean)
    _add_inputs(clean)
    _add_processing(clean)
    _add_filters(clean)
    _add_groups(clean)
    clean.add_argument("-o", "--output", metavar="FILE", help="output file (default: stdout)")
    clean.add_argument(
        "--format",
        dest="out_format",
        choices=("txt", "csv", "json", "jsonl"),
        help="output format (default: detect from extension, else txt)",
    )
    clean.add_argument("--stats", action="store_true", help="print the statistics dashboard")
    clean.add_argument("--report", metavar="FILE", help="write a .json/.csv/.html report")
    clean.add_argument("--invalid-output", metavar="FILE", help="export invalid URLs with reasons")
    clean.add_argument(
        "--duplicates-output", metavar="FILE", help="export the duplicate analysis report"
    )
    clean.add_argument(
        "--extract-features",
        action="store_true",
        help="extract per-URL features (see --features-output)",
    )
    clean.add_argument(
        "--features-output", metavar="FILE", help="feature export file (.jsonl or .csv)"
    )
    clean.add_argument(
        "--redact-userinfo",
        action="store_true",
        help="redact user:password credentials in all output",
    )
    clean.add_argument(
        "--sort",
        choices=("none", "url", "host", "category"),
        help="sort the output (buffers the dataset in memory)",
    )

    # analyze --------------------------------------------------------------
    analyze = sub.add_parser("analyze", help="statistics, classification and Top-N reports")
    _add_common(analyze)
    _add_inputs(analyze)
    _add_processing(analyze)
    _add_filters(analyze)
    analyze.add_argument("--report", metavar="FILE", help="write a .json/.csv/.html report")
    analyze.add_argument(
        "--extract-features",
        action="store_true",
        help="extract per-URL features (see --features-output)",
    )
    analyze.add_argument(
        "--features-output", metavar="FILE", help="feature export file (.jsonl or .csv)"
    )
    analyze.add_argument(
        "--redact-userinfo",
        action="store_true",
        help="redact user:password credentials in all output",
    )

    # diff -----------------------------------------------------------------
    diff = sub.add_parser("diff", help="differential analysis of two datasets")
    _add_common(diff)
    diff.add_argument("old", metavar="OLD", help="old dataset file")
    diff.add_argument("new", metavar="NEW", help="new dataset file")
    _add_processing(diff)
    diff.add_argument(
        "--input-format",
        choices=("txt", "csv", "json", "jsonl"),
        help="force the input format for both files",
    )
    diff.add_argument("--url-column", metavar="COL")
    diff.add_argument("--json-field", metavar="FIELD")
    diff.add_argument(
        "--diff-json",
        nargs="?",
        const="diff.json",
        metavar="FILE",
        help="export the diff as JSON (default file: diff.json)",
    )
    diff.add_argument(
        "--diff-csv",
        nargs="?",
        const="diff.csv",
        metavar="FILE",
        help="export the diff as CSV (default file: diff.csv)",
    )
    diff.add_argument(
        "--diff-txt",
        nargs="?",
        const="diff.txt",
        metavar="FILE",
        help="export the diff as text (default file: diff.txt)",
    )

    # inspect ----------------------------------------------------------------
    inspect = sub.add_parser("inspect", help="inspect one URL (no network activity)")
    _add_common(inspect)
    inspect.add_argument("url", metavar="URL", help="the URL to inspect")
    inspect.add_argument("--profile", choices=[p.value for p in Profile])
    inspect.add_argument(
        "--show-userinfo", action="store_true", help="display credentials instead of redacting them"
    )

    # config ------------------------------------------------------------------
    config_cmd = sub.add_parser("config", help="show the effective configuration")
    _add_common(config_cmd)
    config_cmd.add_argument("--json", action="store_true", help="emit JSON instead of TOML-ish")

    # version -------------------------------------------------------------------
    sub.add_parser("version", help="show version and author information")
    return parser


# ---------------------------------------------------------------------------
# Shared behaviour
# ---------------------------------------------------------------------------


def _setup_logging(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING
    handler: logging.Handler | None = None
    if getattr(args, "log", None):

        class _RedactFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                if record.args:
                    record.msg = redact(str(record.msg))
                    record.args = None
                return True

        handler = logging.FileHandler(args.log, encoding="utf-8")
        if args.log_format == "json":

            class _JSONFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    payload = {
                        "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": redact(record.getMessage()),
                    }
                    return json.dumps(payload)

            handler.setFormatter(_JSONFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
            )
        handler.addFilter(_RedactFilter())
    logging.basicConfig(level=level, handlers=[handler] if handler else [], force=True)
    if handler is None:
        logging.getLogger("urluniq").addHandler(logging.NullHandler())


def _apply_overrides(config: Config, args: argparse.Namespace) -> None:
    """Apply CLI arguments over configuration-file settings."""
    if getattr(args, "profile", None):
        config.profile = Profile(args.profile)
    if getattr(args, "dedupe", None):
        config.dedupe.mode = DedupeMode(args.dedupe)
    if getattr(args, "backend", None):
        config.performance.backend = Backend(args.backend).value
    if getattr(args, "db", None):
        config.performance.sqlite_path = args.db
    if getattr(args, "resume", False):
        config.performance.resume = True
    if getattr(args, "workers", None) is not None:
        config.performance.workers = max(1, args.workers)
    if getattr(args, "hash_algo", None):
        config.dedupe.hash_algorithm = HashAlgorithm(args.hash_algo)
        config.dedupe.use_hash_keys = True
    if getattr(args, "remove_tracking", False):
        config.normalization.remove_tracking_params = True
    if getattr(args, "keep_param", None):
        config.query.keep_params.extend(args.keep_param)
    if getattr(args, "drop_param", None):
        config.query.drop_params.extend(args.drop_param)
    filters = config.filters
    if getattr(args, "domain", None):
        filters.domain = args.domain
    if getattr(args, "include_subdomains", False):
        filters.include_subdomains = True
    for name in ("host", "extension", "path", "regex"):
        include = getattr(args, f"include_{name}", None)
        exclude = getattr(args, f"exclude_{name}", None)
        if include:
            getattr(filters, f"include_{name}").extend(include)
        if exclude:
            getattr(filters, f"exclude_{name}").extend(exclude)


def _registry(config: Config) -> PluginRegistry:
    registry = load_plugins(enabled=config.plugins.enabled, config=config)
    if registry.tracking_params:
        config.add_tracking_params(registry.tracking_params)
    return registry


def _print_banner(args: argparse.Namespace, extra: dict[str, str]) -> None:
    if getattr(args, "quiet", False) or not sys.stderr.isatty():
        return
    sys.stderr.write(BANNER)
    sys.stderr.write(f"\n{APP_SUBTITLE}\n\n")
    sys.stderr.write(f"Version   : {__version__}\n")
    sys.stderr.write(f"Author    : {AUTHOR}\n")
    for label, value in extra.items():
        sys.stderr.write(f"{label:<10}: {value}\n")
    sys.stderr.write("\n")


def _resolve_inputs(args: argparse.Namespace) -> tuple[list[Path], bool]:
    inputs = [Path(p) if p != "-" else Path("-") for p in args.input]
    stdin_used = any(p == Path("-") for p in inputs)
    inputs = [p for p in inputs if p != Path("-")]
    if not inputs and not getattr(args, "input_dir", None):
        if not sys.stdin.isatty():
            return [], True
        raise _UsageError(
            "no input specified (use -i FILE, --input-dir DIR, or pipe URLs on stdin)",
        )
    return inputs, stdin_used


def _read_urls(path: Path, args: argparse.Namespace) -> list[str]:
    fmt = getattr(args, "input_format", None) or detect_format(path)
    column: str | int | None = getattr(args, "url_column", None)
    if isinstance(column, str) and column.isdigit():
        column = int(column)
    return list(iter_input(path, fmt, column, getattr(args, "json_field", None)))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_clean(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    _apply_overrides(config, args)
    _setup_logging(args)
    registry = _registry(config)
    inputs, stdin_used = _resolve_inputs(args)
    output = Path(args.output) if args.output else None
    _print_banner(
        args,
        {
            "Mode": "clean",
            "Input": ", ".join(str(p) for p in inputs) or ("<stdin>" if stdin_used else ""),
            "Output": str(output) or "<stdout>",
            "Profile": config.profile.value,
            "Dedupe": config.dedupe.mode.value,
            "Backend": config.performance.backend,
            "Workers": str(config.performance.workers),
        },
    )
    logger.info("startup: urluniq clean version=%s", __version__)

    features_output = Path(args.features_output) if args.features_output else None
    if args.extract_features and features_output is None:
        features_output = Path("features.jsonl")
        if not args.quiet:
            sys.stderr.write(
                "note: --extract-features without --features-output; "
                f"writing to {features_output}\n"
            )

    url_column: str | int | None = args.url_column
    if isinstance(url_column, str) and url_column.isdigit():
        url_column = int(url_column)

    options = ProcessorOptions(
        inputs=inputs,
        input_dir=Path(args.input_dir) if args.input_dir else None,
        recursive=args.recursive,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        input_format=args.input_format,
        url_column=url_column,
        json_field=args.json_field,
        output=output,
        output_format=args.out_format,
        invalid_output=Path(args.invalid_output) if args.invalid_output else None,
        duplicates_output=Path(args.duplicates_output) if args.duplicates_output else None,
        features_output=features_output,
        report=Path(args.report) if args.report else None,
        group_endpoint=Path(args.group_endpoint) if args.group_endpoint else None,
        group_host=Path(args.group_host) if args.group_host else None,
        group_domain=Path(args.group_domain) if args.group_domain else None,
        group_subdomain=Path(args.group_subdomain) if args.group_subdomain else None,
        group_path=Path(args.group_path) if args.group_path else None,
        use_stdin=stdin_used,
        explain=args.explain,
        extract_features=args.extract_features,
        redact_userinfo=args.redact_userinfo,
        stats=args.stats,
        sort=args.sort or "none",
        classifier_rules=list(registry.classifier_rules),
    )
    processor = Processor(config, options)
    result = processor.run()

    dashboard_stream = sys.stdout if output is not None else sys.stderr
    if args.stats and not args.quiet:
        dashboard_stream.write(render_dashboard(result.stats) + "\n")
    if args.classify and not args.quiet:
        dashboard_stream.write(render_classification_summary(result.stats) + "\n")
    logger.info("completion: clean finished")
    return ExitCode.SUCCESS


def cmd_analyze(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    _apply_overrides(config, args)
    _setup_logging(args)
    registry = _registry(config)
    inputs, stdin_used = _resolve_inputs(args)
    _print_banner(
        args,
        {
            "Mode": "analyze",
            "Input": ", ".join(str(p) for p in inputs) or "<stdin>",
            "Profile": config.profile.value,
            "Dedupe": config.dedupe.mode.value,
        },
    )
    logger.info("startup: urluniq analyze version=%s", __version__)

    url_column: str | int | None = getattr(args, "url_column", None)
    if isinstance(url_column, str) and url_column.isdigit():
        url_column = int(url_column)

    options = ProcessorOptions(
        inputs=inputs,
        input_dir=Path(args.input_dir) if args.input_dir else None,
        recursive=args.recursive,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        input_format=args.input_format,
        url_column=url_column,
        json_field=args.json_field,
        report=Path(args.report) if args.report else None,
        features_output=Path(args.features_output) if args.features_output else None,
        extract_features=args.extract_features,
        redact_userinfo=args.redact_userinfo,
        use_stdin=stdin_used,
        classify=True,
        emit_urls=False,
        classifier_rules=list(registry.classifier_rules),
    )
    result = Processor(config, options).run()

    if not args.quiet:
        sys.stdout.write(render_dashboard(result.stats) + "\n")
        sys.stdout.write(render_classification_summary(result.stats) + "\n\n")
        stats = result.stats
        for title, counter in (
            ("hosts", stats.hosts),
            ("domains", stats.domains),
            ("paths", stats.paths),
            ("extensions", stats.extensions),
            ("parameters", stats.params),
        ):
            sys.stdout.write(render_top(title, counter, config.output.top_n) + "\n\n")
    logger.info("completion: analyze finished")
    return ExitCode.SUCCESS


def cmd_diff(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    _apply_overrides(config, args)
    _setup_logging(args)
    _registry(config)
    old_path, new_path = Path(args.old), Path(args.new)
    for path in (old_path, new_path):
        if not path.is_file():
            raise InputError(f"input not found: {path}")
    _print_banner(args, {"Mode": "diff", "Old": str(old_path), "New": str(new_path)})

    pipeline = URLPipeline(config)
    old_urls = _read_urls(old_path, args)
    new_urls = _read_urls(new_path, args)
    result = compute_diff(pipeline, old_urls, new_urls)

    if not args.quiet:
        sys.stdout.write("=" * 48 + "\nURLUNIQ DIFF\n" + "=" * 48 + "\n")
        for line in result.summary_lines():
            sys.stdout.write(line + "\n")
        _print_samples(result)
    if args.diff_json:
        export_json(Path(args.diff_json), result)
    if args.diff_csv:
        export_csv(Path(args.diff_csv), result)
    if args.diff_txt:
        export_txt(Path(args.diff_txt), result)
    logger.info("completion: diff finished")
    return ExitCode.SUCCESS


def _print_samples(result: DiffResult, limit: int = 8) -> None:
    def block(title: str, urls: list[str]) -> None:
        if urls:
            sys.stdout.write(f"\n{title} ({len(urls)}):\n")
            for url in urls[:limit]:
                sys.stdout.write(f"  {redact(url)}\n")

    block("NEW", [e.new_url for e in result.new])
    block("REMOVED", [e.old_url for e in result.removed])
    if result.changed:
        sys.stdout.write(f"\nMODIFIED/CANONICALIZED ({len(result.changed)}):\n")
        for entry in result.changed[:limit]:
            sys.stdout.write(f"- {redact(entry.old_url)}\n+ {redact(entry.new_url)}\n")


def cmd_inspect(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    _apply_overrides(config, args)
    _setup_logging(args)
    registry = _registry(config)
    from urluniq.classifiers.classifier import URLClassifier
    from urluniq.core.pipeline import PipelineOptions

    classifier = URLClassifier(config.extension_map(), extra_rules=list(registry.classifier_rules))
    redact_info = not args.show_userinfo
    pipeline = URLPipeline(
        config,
        options=PipelineOptions(redact_userinfo=redact_info),
        classifier=classifier,
    )
    record = pipeline.process(args.url)

    out: IO[str] = sys.stdout
    w = out.write
    w("=" * 48 + "\nURLUNIQ INSPECT\n" + "=" * 48 + "\n\n")
    w(f"Original URL      : {redact(args.url)}\n")
    if record.error:
        w(f"Status            : INVALID - {record.error}\n")
        return ExitCode.SUCCESS
    parsed = _parsed(record.normalized)
    _ = parsed
    w("Status            : valid\n")
    w(f"Normalized URL    : {record.normalized}\n")
    w(f"Canonical URL     : {record.canonical}\n")
    w(f"Scheme            : {record.scheme}\n")
    w(f"Host              : {record.host}\n")
    w(f"Subdomain         : {record.subdomain or '(none)'}\n")
    w(f"Registrable domain: {record.registrable_domain}\n")
    w(f"Port              : {record.port or '(default)'}\n")
    w(f"Path              : {record.path or '/'}\n")
    w(f"Query             : {record.query or '(none)'}\n")
    w(
        f"Parameters        : {record.param_count}"
        + (f" ({', '.join(record.param_names)})" if record.param_names else "")
        + "\n"
    )
    fragment_state = "present (removed by profile)" if record.has_fragment else "absent"
    w(f"Fragment          : {fragment_state}\n")
    w(
        f"Credentials       : {'present' if record.has_userinfo else 'absent'}"
        + (" (redacted)" if record.has_userinfo and redact_info else "")
        + "\n"
    )
    w(f"Classification    : {record.category}  (heuristic)\n")
    w(f"URL length        : {record.url_length}\n")
    w(f"Path depth        : {record.path_depth}\n")
    w("\nApplied transformations:\n")
    if record.reasons:
        for reason in dict.fromkeys(record.reasons):
            w(f"  - {reason}\n")
    else:
        w("  (none - URL was already in normalized form)\n")
    return ExitCode.SUCCESS


def _parsed(url: str):
    from urluniq.core.parser import parse_url as _parse

    parsed, _err, _reasons = _parse(url)
    return parsed


def cmd_config(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    _setup_logging(args)
    if args.json:
        sys.stdout.write(json.dumps(config.to_dict(), indent=2, default=str) + "\n")
        return ExitCode.SUCCESS
    data = config.to_dict()
    sys.stdout.write(f"URLUNIQ {__version__} effective configuration\n")
    sys.stdout.write("=" * 48 + "\n")
    if config.config_path:
        sys.stdout.write(f"loaded from: {config.config_path}\n")
    else:
        sys.stdout.write("loaded from: built-in defaults\n")
    sys.stdout.write("\n" + _toml_dump(data) + "\n")
    tracking = sorted(config.tracking_params())
    sys.stdout.write(f"\nTracking parameters configured: {len(tracking)}\n")
    data_file = config.resolve_data_file(config.query.tracking_params_file)
    sys.stdout.write(f"Tracking list file : {data_file or '(built-in list)'}\n")
    ext_file = config.resolve_data_file(config.classification.extensions_file)
    sys.stdout.write(f"Extensions file    : {ext_file or '(built-in map)'}\n")
    return ExitCode.SUCCESS


def _toml_dump(data: dict, indent: int = 0) -> str:
    """Render a config dictionary in readable TOML-ish form."""
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}[{key}]")
            lines.append(_toml_dump(value, indent + 1))
        elif isinstance(value, list):
            rendered = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
            lines.append(f"{pad}{key} = [{rendered}]")
        elif isinstance(value, bool):
            lines.append(f"{pad}{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{pad}{key} = {value}")
        elif value is None:
            lines.append(f"{pad}# {key} = (none)")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{pad}{key} = "{escaped}"')
    return "\n".join(lines)


def cmd_version(_args: argparse.Namespace) -> int:
    sys.stdout.write(BANNER)
    sys.stdout.write(f"\n{APP_TITLE} ({__version__})\n")
    sys.stdout.write("Advanced URL Processing Framework\n")
    sys.stdout.write(f"Author  : {AUTHOR}\n")
    sys.stdout.write(f"GitHub  : {GITHUB_URL}\n")
    sys.stdout.write(f"YouTube : {YOUTUBE_URL}\n")
    sys.stdout.write(f"\n{PRIMARY_TAGLINE}\n{SECONDARY_TAGLINE}\n")
    return ExitCode.SUCCESS


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    "clean": cmd_clean,
    "analyze": cmd_analyze,
    "diff": cmd_diff,
    "inspect": cmd_inspect,
    "config": cmd_config,
    "version": cmd_version,
}


class _UsageError(URLUNIQError):
    exit_code = ExitCode.INVALID_ARGUMENTS


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = build_parser()
    raw_args = list(sys.argv[1:]) if argv is None else list(argv)
    args = parser.parse_args(raw_args)
    if not args.command:
        if raw_args:
            parser.print_help()
            return ExitCode.INVALID_ARGUMENTS
        if not sys.stdin.isatty():
            # ``cat urls.txt | urluniq`` -> implicit ``clean``.
            args = parser.parse_args(["clean"])
        else:
            parser.print_help()
            return ExitCode.INVALID_ARGUMENTS
    handler = _HANDLERS[args.command]
    try:
        return int(handler(args))
    except URLUNIQError as exc:
        if getattr(args, "debug", False):
            logger.exception("failed")
        sys.stderr.write(f"urluniq: error: {exc}\n")
        return int(getattr(exc, "exit_code", ExitCode.GENERAL_ERROR))
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        sys.stderr.write("\nurluniq: interrupted\n")
        return 130
    except OSError as exc:
        sys.stderr.write(f"urluniq: error: {exc}\n")
        return int(ExitCode.GENERAL_ERROR)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
