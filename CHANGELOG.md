# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-09-06

The advanced-framework release. URLUNIQ grows from a duplicate remover into a
full offline URL processing pipeline for bug-bounty recon, security research
and web-asset organization.

### Added

- **Canonicalization engine** with safe/standard/aggressive profiles.
- **Profiles**: `--profile safe|standard|aggressive`, customizable via TOML.
- **Smart deduplication**: exact, normalized, canonical, host, path,
  path+query and configurable "smart" strategies.
- **Parameter engine**: tracking-parameter removal, allow/deny lists,
  duplicate-parameter detection, session-parameter detection.
- **URL classification** (heuristic): API, HTML, JS, CSS, image, document,
  auth, logout, search, download, upload, redirect, parameterized,
  extensionless and more.
- **Feature extraction** (`--extract-features`) to JSON/CSV.
- **Host / domain / subdomain / path grouping** and Top-N reports.
- **Differential analysis**: `urluniq diff old.txt new.txt` with
  `--diff-json/--diff-csv/--diff-txt` exports.
- **Duplicate analysis reports** showing canonical URL, variants and counts.
- **Transformation explanations** (`--explain`) recording why each URL changed.
- **SQLite deduplication backend** (`--backend sqlite --db urluniq.db`) with
  indexes and `--resume` support for interrupted runs.
- **HTML / JSON / CSV report generation** (fully offline, no external assets).
- **Invalid-URL dataset export** (`--invalid-output`) with error reasons.
- **Streaming pipeline** with progress reporting, optional multiprocessing
  (`--workers`) and memory-aware operation for multi-million-URL inputs.
- **Configurable hashing** (`--hash sha256|sha1|md5|xxhash`).
- **Input formats**: TXT, CSV, JSON, JSONL, stdin.
- **Output formats**: TXT, CSV, JSON, JSONL.
- **Filtering engine**: include/exclude by host, extension, path and regex;
  domain scoping with optional subdomains.
- **Plugin architecture** for custom normalizers, classifiers, filters and
  exporters.
- **Python library API** (`normalize_url`, `canonicalize_url`,
  `deduplicate_urls`, ...).
- **Benchmark suite** (`benchmarks/run_benchmark.py`).
- **Structured logging** with text/JSON formats and credential redaction.
- Meaningful **exit codes** (0/1/2/3/4/5) documented in the README.
- Full test suite (unit + integration + large-data regression tests).

## [1.5.0] - 2026-02-14

### Added

- URL normalization (scheme/host casing, default ports, fragments).
- Multiple input formats: TXT, CSV.
- Improved CLI: progress display, statistics, quiet mode.
- Configurable output sorting.

## [1.0.0] - 2025-11-02

### Added

- Initial release: basic exact-match URL deduplication from text files.
- Simple CLI: `urluniq -i urls.txt -o clean.txt`.
