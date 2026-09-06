# URLUNIQ 2.0

### Advanced URL Normalization, Canonicalization & Deduplication Framework

![URLUNIQ](assets/logo.svg)

**"Normalize. Canonicalize. Deduplicate. Analyze."**
*"Millions of URLs. One clean dataset."*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-8b949e)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-354%20passing-7ee787)](tests)
[![Zero runtime deps](https://img.shields.io/badge/dependencies-0-success)](pyproject.toml)

**Author:** [mrdineshpathro-dot](https://github.com/mrdineshpathro-dot) &nbsp;·&nbsp;
**GitHub:** https://github.com/mrdineshpathro-dot &nbsp;·&nbsp;
**YouTube:** https://www.youtube.com/@GithubHacker

URLUNIQ turns messy crawled, scraped and recon URL lists into clean,
deduplicated, classified datasets — **completely offline**. Built for
bug-bounty reconnaissance, security research, web-asset organization,
endpoint inventory preparation, crawling-data cleanup and large-scale URL
dataset processing.

> URLUNIQ only processes URLs you give it. It never sends requests, never
> resolves DNS and never executes URLs. See [Security notes](#security-notes).

---

## Table of contents

1. [Features](#features)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [Sample transformation walkthrough](#sample-transformation-walkthrough)
5. [CLI reference](#cli-reference)
6. [Normalization profiles](#normalization-profiles)
7. [Deduplication modes](#deduplication-modes)
8. [Query parameter engine](#query-parameter-engine)
9. [Classification](#classification)
10. [Filtering](#filtering)
11. [Feature extraction](#feature-extraction)
12. [Grouping and Top-N](#grouping-and-top-n)
13. [Diff mode](#diff-mode)
14. [Duplicate analysis](#duplicate-analysis)
15. [Reports](#reports)
16. [Configuration](#configuration)
17. [Library usage](#library-usage)
18. [Performance](#performance)
19. [Benchmarks](#benchmarks)
20. [Testing](#testing)
21. [Architecture](#architecture)
22. [Plugins](#plugins)
23. [Exit codes](#exit-codes)
24. [Security notes](#security-notes)
25. [Responsible use](#responsible-use)
26. [Contributing](#contributing)
27. [License](#license)

---

## Features

- **Pipeline engine** — Parsing → Validation → Normalization →
  Canonicalization → Filtering → Deduplication → Classification →
  Sorting/Grouping → Export → Statistics. Every stage is independently
  testable.
- **Three normalization profiles** — `safe`, `standard` (default),
  `aggressive` — every rule configurable through TOML.
- **30+ normalization rules** — scheme/host casing, IDN/punycode,
  default-port removal, dot-segment removal, duplicate-slash collapsing,
  RFC 3986 percent-encoding normalization, trailing-slash consistency,
  query sorting, fragment removal, IPv4/IPv6 canonicalization and more.
- **Seven deduplication strategies** — `exact`, `normalized`, `canonical`,
  `host`, `path`, `path_query`, `smart`.
- **Smart query-parameter engine** — tracking-parameter removal, allow/deny
  lists, duplicate-parameter handling, session-parameter detection.
- **Heuristic classification** — API, HTML, JS, CSS, Image, Document, Auth,
  Logout, Search, Download, Upload, Redirect, Parameterized, Extensionless…
- **Feature extraction** — 18 per-URL features exported to JSON/CSV.
- **Differential analysis** — `diff` two datasets (new / removed /
  unchanged / modified).
- **Duplicate analysis reports** — canonical URL, original variants, counts
  and reasons instead of silent deletion.
- **Transformation explanations** — `--explain` records *why* each URL changed.
- **Streaming + multiprocessing** — chunked processing, progress reporting,
  optional `--workers N`.
- **SQLite backend** — persistent, indexed deduplication for datasets bigger
  than RAM, with `--resume`.
- **Reports** — standalone offline HTML, JSON and CSV reports with full
  reproducibility metadata.
- **Formats** — TXT/CSV/JSON/JSONL in, TXT/CSV/JSON/JSONL out, stdin piping.
- **Python library** — clean, type-hinted public API.
- **Zero runtime dependencies** — Python 3.10+ standard library only
  (`xxhash` optional).

## Installation

```bash
# from a clone of this repository
pip install -e .

# with development tooling
pip install -e ".[dev]"

# optional fast hashing
pip install "urluniq[performance]"   # or: pip install xxhash
```

Verify:

```console
$ urluniq --version
URLUNIQ 2.0.0
```

`urluniq --version` prints the short form; `urluniq version` prints the full
banner with author, GitHub and YouTube links.

## Quick start

```bash
# Basic: normalize + deduplicate
urluniq clean -i urls.txt -o clean.txt

# Standard workflow with tracking removal and stats
urluniq clean -i urls.txt --profile standard --remove-tracking -o clean.txt --stats

# Analyze a dataset (dashboard, classification, Top-N lists)
urluniq analyze -i urls.txt

# Inspect a single URL (offline, no requests)
urluniq inspect "https://example.com/search?q=test&utm_source=x"

# Compare two crawl snapshots
urluniq diff old_urls.txt new_urls.txt

# HTML report
urluniq clean -i urls.txt -o clean.txt --report report.html

# Pipe from another tool (`clean` is the implicit subcommand for piped input)
cat urls.txt | urluniq | sort > sorted.txt
cat urls.txt | urluniq clean --remove-tracking -o clean.txt

# Large datasets: SQLite-backed dedupe + workers
urluniq clean -i huge.txt --backend sqlite --db urluniq.db --workers 8 --stats
```

Real dashboard output (`urluniq clean -i examples/urls.txt --stats -o clean.txt`):

```
================================================
URLUNIQ 2.0 REPORT
================================================
Input URLs          : 8
Valid URLs          : 8
Invalid URLs        : 0
Filtered URLs       : 0
Duplicates          : 4
Unique URLs         : 4
Canonical changes   : 4
Tracking removed    : 0
Parameterized URLs  : 3

Processing time     : 0.00 sec
Processing speed    : 4,878 URLs/sec
================================================
```

## Sample transformation walkthrough

`examples/urls.txt` contains exactly the demo dataset below. Running
`urluniq clean -i examples/urls.txt -o clean.txt` (default `standard`
profile) transforms it like this:

| Input line | Normalized output | What happened |
|---|---|---|
| `HTTP://EXAMPLE.COM:80/` | `http://example.com/` | scheme + host lowercased, default port removed |
| `http://example.com` | `http://example.com/` | empty path expanded to `/` → duplicate of row 1 |
| `https://EXAMPLE.com/` | `https://example.com/` | host lowercased |
| `https://example.com/#home` | `https://example.com/` | fragment removed → duplicate of row 3 |
| `https://example.com` | `https://example.com/` | empty path expanded → duplicate of row 3 |
| `https://example.com/search?q=1&utm_source=test` | `https://example.com/search/?q=1&utm_source=test` | trailing slash added, params sorted |
| `https://example.com/search?utm_source=test&q=1` | `https://example.com/search/?q=1&utm_source=test` | same after sorting → duplicate of row 6 |
| `https://example.com/search?q=1` | `https://example.com/search/?q=1` | trailing slash added |

**Result: 8 input URLs → 4 unique URLs, 4 duplicates.**

The final `clean.txt`:

```
http://example.com/
https://example.com/
https://example.com/search/?q=1&utm_source=test
https://example.com/search/?q=1
```

Add `--remove-tracking --dedupe canonical` and the tracker-variants merge
too — 8 input URLs collapse to **2 unique endpoints**:

```
http://example.com/
https://example.com/search/?q=1
```

## CLI reference

```
urluniq [-h] [-V] COMMAND ...

Commands:
  clean     normalize and deduplicate URLs
  analyze   statistics, classification and Top-N reports
  diff      differential analysis of two datasets
  inspect   inspect one URL (no network activity)
  config    show the effective configuration
  version   show version and author information
```

### `clean`

```text
urluniq clean [-i FILE ...] [--input-dir DIR] [--recursive]
                    [--include PATTERN] [--exclude PATTERN]
                    [--input-format txt|csv|json|jsonl]
                    [--url-column COL] [--json-field FIELD]
                    [-o FILE] [--format txt|csv|json|jsonl]
                    [--profile safe|standard|aggressive]
                    [--dedupe exact|normalized|canonical|host|path|path_query|smart]
                    [--backend memory|sqlite] [--db FILE] [--resume]
                    [--workers N] [--hash sha256|sha1|md5|xxhash]
                    [--remove-tracking] [--keep-param NAME] [--drop-param NAME]
                    [--classify] [--explain]
                    [--domain DOMAIN] [--include-subdomains]
                    [--include-host V] [--exclude-host V]
                    [--include-extension V] [--exclude-extension V]
                    [--include-path V] [--exclude-path V]
                    [--include-regex P] [--exclude-regex P]
                    [--group-by-endpoint [FILE]] [--group-host [FILE]]
                    [--group-domain [FILE]] [--group-subdomain [FILE]]
                    [--group-path [FILE]]
                    [--stats] [--report FILE] [--invalid-output FILE]
                    [--duplicates-output FILE]
                    [--extract-features] [--features-output FILE]
                    [--redact-userinfo] [--sort none|url|host|category]
                    [--config FILE] [--quiet] [--verbose] [--debug]
                    [--log FILE] [--log-format text|json]
```

Output formats are picked from the `-o` extension when possible, so
`-o clean.csv` writes CSV with columns
`url,normalized_url,canonical_url,category` (`changes` is appended with
`--explain`), `-o clean.json` writes a structured array and `-o clean.jsonl`
writes one record per line:

```json
{
  "url": "https://example.com/search?q=1&utm_source=test",
  "normalized_url": "https://example.com/search/?q=1&utm_source=test",
  "canonical_url": "https://example.com/search/?q=1",
  "category": "Search"
}
```

### `analyze`

`urluniq analyze -i urls.txt` prints the dashboard, the classification
table and Top-N hosts/domains/paths/extensions/parameters. It writes no URL
stream, so it is safe to redirect. Example on `examples/urls.csv`:

```
Category          Count
-----------------------
Extensionless         5
Search                3
API                   2
JS                    1
Image                 1
Auth                  1
Document              1
```

### `inspect`

```console
$ urluniq inspect "https://user:secret@example.com/search?q=test&utm_source=x"
================================================
URLUNIQ INSPECT
================================================

Original URL      : https://[REDACTED]@example.com/search?q=test&utm_source=x
Status            : valid
Normalized URL    : https://[REDACTED]@example.com/search/?q=test&utm_source=x
Canonical URL     : https://[REDACTED]@example.com/search/?q=test
Scheme            : https
Host              : example.com
Subdomain         : (none)
Registrable domain: example.com
Port              : 443
Path              : /search/
Query             : q=test&utm_source=x
Parameters        : 2 (q, utm_source)
Fragment          : absent
Credentials       : present (redacted)
Classification    : Search  (heuristic)
URL length        : 58
Path depth        : 1

Applied transformations:
  - trailing slash added
  - credentials redacted
```

Credentials are redacted by default; use `--show-userinfo` to reveal them.

### `config`

`urluniq config` prints the effective configuration (TOML-ish, or `--json`),
which config file was loaded and how many tracking parameters are active.

## Normalization profiles

| Rule | safe | standard | aggressive |
|---|:--:|:--:|:--:|
| Scheme / hostname lowercasing | ✅ | ✅ | ✅ |
| Whitespace / control-char cleanup | ✅ | ✅ | ✅ |
| IDN → punycode | – | ✅ | ✅ |
| Default port removal (`:80`, `:443`) | – | ✅ | ✅ |
| Empty path → `/` | – | ✅ | ✅ |
| Trailing-slash consistency | – | ✅ | ✅ |
| Duplicate-slash collapsing | – | ✅ | ✅ |
| Dot-segment removal (`/a/../b`) | – | ✅ | ✅ |
| Percent-encoding normalization | – | ✅ | ✅ |
| Fragment removal | – | ✅ | ✅ |
| Query-parameter sorting | – | ✅ | ✅ |
| IPv4/IPv6 literal canonicalization | – | ✅ | ✅ |
| Tracking-parameter removal | – | – | ✅ |
| Duplicate-parameter removal | – | – | ✅ |
| `index.html` → directory | – | – | ✅ |
| `www.` stripping *(opt-in)* | – | – | opt-in |
| http → https upgrade *(opt-in)* | – | – | opt-in |

Rules are **semantically safe by construction**: reserved characters stay
percent-encoded (`%2F` is never decoded into `/`), `+` in query values is
never rewritten, and query ordering is preserved in `safe` mode.

Select a profile:

```bash
urluniq clean -i urls.txt --profile safe
urluniq clean -i urls.txt --profile standard
urluniq clean -i urls.txt --profile aggressive
```

Any value can be overridden per profile in `config/default.toml`:

```toml
[profiles.aggressive]
strip_www = true
upgrade_http = false          # default: off (changes resource identity)
remove_empty_params = true
```

The **canonical form** used by `--dedupe canonical`/`smart` is controlled by
the `[canonicalization]` section (defaults: drop fragments, sort + dedupe
parameters, drop tracking parameters, drop index documents, merge http/https).

## Deduplication modes

| Mode | Identity compared | Typical use |
|---|---|---|
| `exact` | raw string | remove literal re-crawls only |
| `normalized` *(default)* | normalized URL | the everyday dedupe |
| `canonical` | canonical identity | merges tracker-variants and http/https |
| `host` | one URL per host | host inventory |
| `path` | host + path | endpoint inventory |
| `path_query` | host + path + meaningful params | endpoint+param inventory |
| `smart` | configurable rules (drops tracking/session/empty params) | recon triage |

```bash
urluniq clean -i urls.txt --dedupe normalized
urluniq clean -i urls.txt --dedupe canonical
urluniq clean -i urls.txt --dedupe smart
```

Parameter-aware grouping (`--group-by-endpoint`) answers the
"`/search?q=1`, `/search?q=2`, `/search?q=3` — same endpoint or different
URLs?" question: each URL stays unique in the clean output, while the group
file clusters them under one endpoint:

```text
# URLUNIQ endpoint groups (2 groups)

[example.com/] (2 URLs)
  http://example.com/
  https://example.com/

[example.com/search/] (2 URLs)
  https://example.com/search/?q=1&utm_source=test
  https://example.com/search/?q=1
```

## Query parameter engine

- `--remove-tracking` — drop tracking parameters (list from
  `config/tracking_params.txt`, fully configurable).
- `--keep-param id` / `--keep-param page` — allowlist.
- `--drop-param utm_source` / `--drop-param fbclid` — denylist.
- Duplicate-parameter detection with `keep first` / `keep last`
  (`query.duplicate_keep`).
- Optional empty-parameter removal (`remove_empty_params`).
- Case-sensitive/insensitive parameter matching
  (`query.case_sensitive_names`).
- Session-parameter detection (`jsessionid`, `phpsessid`, `csrf`, `token`,
  …) used by `smart` dedupe — detection only, never silent removal.

The built-in tracking list lives in **`config/tracking_params.txt`** — edit
it, don't fork the code.

## Classification

`--classify` prints the summary table; categories are always attached to
structured output. Classification is **heuristic only** (path/param/
extension shape — no requests are ever made):

```
API           1540
JS             920
HTML          4380
Images         710
Parameterized 2100
...
```

Categories: `API`, `JS`, `CSS`, `Image`, `Document`, `Static`, `HTML`,
`Auth`, `Logout`, `Search`, `Download`, `Upload`, `Redirect`,
`Parameterized`, `Extensionless`, `Unknown`. Extension→category mappings are
configured in `config/extensions.txt`.

## Filtering

```bash
urluniq clean -i urls.txt --exclude-extension jpg
urluniq clean -i urls.txt --include-host example.com
urluniq clean -i urls.txt --domain example.com --include-subdomains
urluniq clean -i urls.txt --include-path /api/ --exclude-path /static/
urluniq clean -i urls.txt --include-regex '/v[0-9]+/' --exclude-regex '\.png$'
```

Regex filtering is **explicit and optional**. Domain scoping never resolves
DNS — it only filters the dataset.

## Feature extraction

```bash
urluniq clean -i urls.txt -o clean.txt --extract-features --features-output features.jsonl
```

Exports scheme, host, subdomain, registrable domain, port, path, directory,
filename, extension, query-parameter count and names, fragment presence, URL
length, path depth, and category — one JSON object per unique URL (or CSV
with `--features-output features.csv`).

## Grouping and Top-N

```bash
urluniq clean -i urls.txt --group-host hosts.txt --group-domain domains.txt
urluniq clean -i urls.txt --group-subdomain subs.txt --group-path paths.txt
urluniq clean -i urls.txt --group-by-endpoint endpoints.txt
```

`analyze` additionally prints Top hosts, Top domains, Top paths, Top
extensions, Top parameters and the largest URLs.

## Diff mode

```console
$ urluniq diff examples/old_urls.txt examples/new_urls.txt
================================================
URLUNIQ DIFF
================================================
New:       4
Removed:   4
Unchanged: 2
Changed:   0

NEW (4):
  https://api.example.com/v1/users?page=1&mode=full
  https://example.com/login?next=/home
  https://example.com/search?q=2
  https://new.example.com/panel

REMOVED (4):
  ...
```

Export with `--diff-json`, `--diff-csv` or `--diff-txt` (each accepts an
optional path, defaulting to `diff.json` / `diff.csv` / `diff.txt`).
"Changed" = same canonical identity, different raw/normalized variant.

## Duplicate analysis

`--duplicates-output duplicates.txt` keeps the evidence instead of silently
deleting URLs:

```text
CANONICAL:
https://example.com/

VARIANTS:
https://EXAMPLE.com/
https://example.com/#home
https://example.com

COUNT:
3
```

Every transformed URL can also explain itself with `--explain`, which adds a
`changes` list to structured output; `inspect` always shows the reasons:

```
Original:    HTTP://EXAMPLE.COM:80/path/#section
Normalized:  http://example.com/path/
Changes:     hostname lowercased · default port removed ·
             fragment removed · trailing slash normalized
```

## Reports

```bash
urluniq clean -i urls.txt -o clean.txt --report report.html   # standalone HTML
urluniq clean -i urls.txt -o clean.txt --report report.json   # machine readable
urluniq clean -i urls.txt -o clean.txt --report report.csv    # spreadsheet
```

The HTML report (summary cards, input/duplicate/normalization statistics,
hosts, domains, extensions, parameters, categories, largest URLs, example
transformations, duplicate clusters, error summary) embeds its CSS and
references **no external network resources**. Every report records version,
Python version, OS, profile, configuration, command line, timestamp and
input/output filenames for reproducibility. Existing `.html` reports are
backed up (`.bak`) instead of overwritten.

Invalid URLs can be exported with reasons instead of dropped:

```bash
urluniq clean -i urls.txt -o clean.txt --invalid-output invalid.txt
# invalid.txt: "<url>\t<reason>" (invalid scheme, malformed hostname, ...)
```

## Configuration

```bash
urluniq --config config/default.toml clean -i urls.txt
urluniq config          # show effective configuration
```

Resolution order for `default.toml`: the `--config` path → `./config/default.toml`
→ the copy bundled inside the package. CLI arguments always win over file
settings. Key sections:

| Section | Controls |
|---|---|
| `[normalization]` | global rule switches (all profiles) |
| `[profiles.*]` | per-profile overrides |
| `[canonicalization]` | canonical identity rules |
| `[query]` | tracking list file, keep/drop lists, duplicate policy |
| `[dedupe]` | mode, hash algorithm, smart rules |
| `[classification]` | extensions file |
| `[filters]` | static include/exclude lists, domain scope |
| `[output]` | format, sort, top-N, duplicate report caps |
| `[performance]` | workers, backend, chunk size, cache, progress |
| `[logging]` | log file, format, level |
| `[validation]` | allowed schemes, max URL length |
| `[plugins]` | plugin enable switches |

Data files: `config/tracking_params.txt`, `config/extensions.txt` (also
bundled in `src/urluniq/data/` so `pip install` ships them).

## Library usage

```python
from urluniq import normalize_url, canonicalize_url, deduplicate_urls, classify_url

result = normalize_url("HTTP://EXAMPLE.COM:80/test/#section")
print(result)            # http://example.com/test/
print(result.changes)    # ['default port removed', 'fragment removed']

result = canonicalize_url("https://example.com/s?q=1&utm_source=x")
print(result.canonical)  # https://example.com/s/?q=1

print(classify_url("https://api.example.com/v1/users"))  # "API"

clean = deduplicate_urls(
    ["http://EXAMPLE.com:80/a", "http://example.com/a", "https://b.com/x"],
    mode="normalized",
)
print(len(clean))        # 2
print(list(clean))       # ['http://example.com/a/', 'https://b.com/x/']
print(clean.stats)       # {'input': 3, 'unique': 2, 'duplicates': 1, 'invalid': 0}
```

Full type hints, docstrings and `py.typed` are included. Lower-level APIs:
`urluniq.parse_url`, `URLPipeline`, `Processor`, `Config`, `DedupeEngine`,
`SQLiteStore`, `URLClassifier` — see the module docstrings.

## Performance

- Streaming input with buffered IO; memory use stays flat.
- Per-run result cache exploits duplicate-heavy datasets (most recon data).
- Multiprocessing (`--workers N`) engages automatically only above
  `[performance] multiprocess_min_lines` — small files never pay the fork tax.
- `--backend sqlite` swaps RAM for an indexed on-disk identity table.
- Progress is shown only on interactive terminals (never when piped or
  `--quiet`).

Typical single-core throughput on the bundled benchmark generator
(Python 3.11, results vary by machine): ~200,000 URLs/sec on a
duplicate-heavy 1M-URL dataset, ~30,000 URLs/sec on worst-case
mostly-unique data.

## Benchmarks

```bash
python benchmarks/run_benchmark.py                  # 10K + 100K
python benchmarks/run_benchmark.py --sizes 1000000
python benchmarks/run_benchmark.py --full           # 10K..5M
python benchmarks/run_benchmark.py --json out.json
```

Measures runtime, URLs/sec and peak RSS through the real processing path:

```
      URLs |   runtime |    urls/sec |  peak RSS |   unique |     dups |  invalid
------------------------------------------------------------------------------
    10,000 |    0.32s  |      31,645 |    26.7MB |    1,793 |    8,207 |        0
   100,000 |    0.99s  |     100,891 |    31.9MB |    2,239 |   97,761 |        0
 1,000,000 |    4.83s  |     207,052 |    36.0MB |    2,240 |  997,760 |        0
```

*(Python 3.11, sandboxed container — rerun `run_benchmark.py` on your own
hardware for authoritative numbers.)*

## Testing

```bash
pip install -e ".[dev]"
pytest                        # 354 tests: unit + integration + large-data
make test                     # same, via the Makefile
make check                    # ruff + mypy + pytest
```

Coverage areas: URL parsing, normalization (every rule), canonicalization,
query/parameter handling, fragments, ports, Unicode/IDN domains, IPv4,
IPv6, malformed URLs, all dedupe modes, sorting, filtering, classification,
TXT/CSV/JSON/JSONL input, stdin, exporters, reports, diff mode, SQLite
backend (including resume), configuration, the CLI, exit codes and 100K-URL
large-data runs (single-process, multiprocess and SQLite).

## Architecture

```
src/urluniq/
├── core/         parser, validator, pipeline, processor, diff
├── normalizers/  base engine + safe/standard/aggressive presets
├── dedupe/       engine, strategies, hashing
├── classifiers/  heuristic rules
├── filters/      include/exclude engine
├── parsers/      txt, csv, json, jsonl input
├── exporters/    txt, csv, json, jsonl output
├── reports/      statistics, json/csv/html reports
├── storage/      memory + sqlite backends
├── config/       TOML loader (tomllib + built-in 3.10 fallback)
└── plugins/      registry + example plugin
```

Design rules: type hints everywhere, dataclasses/enums, no global mutable
state, small testable functions, no hardcoded absolute paths.

## Plugins

Drop a module into `src/urluniq/plugins/` defining
`register(registry[, config])` and it is loaded automatically (disable with
`[plugins] enabled = false`). Plugins can register tracking parameters,
classifier rules, filters and exporters. See `plugins/example.py`.
Plugins are passive — URLUNIQ never executes external commands for a plugin
and never evaluates untrusted input at import time.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | general error |
| 2 | invalid arguments |
| 3 | input error (missing/unreadable input) |
| 4 | output error (unwritable output/report) |
| 5 | configuration error |

## Security notes

- URLUNIQ **never** fetches, pings, resolves or executes URLs. All work is
  offline string processing.
- Credentials in URLs (`https://user:pass@host/`) are **redacted by
  default** in logs, `inspect` output and reports; pass `--redact-userinfo`
  to also redact the clean output, or `inspect --show-userinfo` to reveal.
- Invalid URLs are rejected into a separate dataset (`--invalid-output`)
  with reasons; untrusted input is parsed defensively (length caps, control
  characters, malformed ports/hosts).
- Report files are never silently overwritten (`.html` gets a `.bak`).
- `javascript:`, `data:` and other schemes are rejected as invalid by
  default (`[validation] allowed_schemes`).

## Responsible use

URLUNIQ is a defensive data-hygiene tool. Use it on datasets you collected
legally and are authorized to hold. The tool performs no exploitation,
credential attacks, brute force, unauthorized scanning or any destructive
network activity — and it is not intended to assist with any of those.

## Contributing

1. Fork / branch from `main`.
2. `pip install -e ".[dev]"` and keep `make check` green
   (ruff + black + mypy + pytest).
3. Add tests for every fix or feature; regression tests for every bug.
4. Send a PR describing the motivation and the change.

## License

MIT — see [LICENSE](LICENSE).

## Author

**mrdineshpathro-dot**

- GitHub: https://github.com/mrdineshpathro-dot
- YouTube: https://www.youtube.com/@GithubHacker
- Repository: https://github.com/mrdineshpathro-dot/URLUNIQ

---

URLUNIQ 2.0.0 · Normalize. Canonicalize. Deduplicate. Analyze. · Millions of URLs. One clean dataset.
