"""Standalone HTML report writer (``--report report.html``).

The report embeds its CSS inline and references no external network
resources, so it renders identically offline.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from urluniq.constants import APP_TITLE, AUTHOR, GITHUB_URL, PRIMARY_TAGLINE, YOUTUBE_URL
from urluniq.reports.statistics import RunResult, render_dashboard

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
       margin: 0; background: #0d1117; color: #c9d1d9; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
header { border-bottom: 1px solid #30363d; padding-bottom: 1rem; margin-bottom: 2rem; }
h1 { font-size: 1.6rem; letter-spacing: .08em; margin: 0; color: #58a6ff; }
h1 small { display:block; font-size: .8rem; color:#8b949e; letter-spacing:.2em; }
h2 { font-size: 1.05rem; color: #7ee787; border-bottom: 1px solid #21262d;
     padding-bottom: .3rem; margin-top: 2.2rem; }
.tagline { color: #8b949e; font-style: italic; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
         gap: .8rem; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: .9rem; }
.card .num { font-size: 1.4rem; font-weight: 700; color: #58a6ff; }
.card .lbl { font-size: .75rem; color: #8b949e; text-transform: uppercase;
             letter-spacing: .06em; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #21262d; }
th { color: #8b949e; text-transform: uppercase; font-size: .7rem; letter-spacing: .08em; }
td.num, th.num { text-align: right; }
pre { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
      padding: 1rem; overflow-x: auto; font-size: .78rem; }
footer { margin-top: 3rem; color: #8b949e; font-size: .78rem; border-top: 1px solid #21262d;
         padding-top: 1rem; }
a { color: #58a6ff; text-decoration: none; }
.warn { color: #d29922; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _cards(stats: Any) -> str:
    items = (
        ("Input", f"{stats.input_urls:,}"),
        ("Valid", f"{stats.valid_urls:,}"),
        ("Invalid", f"{stats.invalid_urls:,}"),
        ("Duplicates", f"{stats.duplicates:,}"),
        ("Unique", f"{stats.unique_urls:,}"),
        ("Speed", f"{stats.speed:,.0f}/s"),
    )
    cells = "".join(
        f'<div class="card"><div class="num">{_esc(num)}</div>'
        f'<div class="lbl">{_esc(label)}</div></div>'
        for label, num in items
    )
    return f'<div class="cards">{cells}</div>'


def _top_table(title: str, counter: Any, limit: int) -> str:
    if not counter:
        return f"<h2>{_esc(title)}</h2><p class='warn'>(none)</p>"
    rows = "".join(
        f"<tr><td>{_esc(key)}</td><td class='num'>{count:,}</td></tr>"
        for key, count in counter.most_common(limit)
    )
    return (
        f"<h2>{_esc(title)}</h2><table><tr><th>Entry</th><th class='num'>Count</th></tr>"
        f"{rows}</table>"
    )


def _examples(result: RunResult) -> str:
    if not result.stats.examples:
        return "<h2>Example transformations</h2><p class='warn'>(no URLs changed)</p>"
    blocks = []
    for example in result.stats.examples[:15]:
        changes = "<br>".join(_esc(f"- {c}") for c in example["changes"][:8])
        blocks.append(
            f"<p><strong>Original:</strong> {_esc(example['original'])}<br>"
            f"<strong>Normalized:</strong> {_esc(example['normalized'])}<br>"
            f"<strong>Changes:</strong><br>{changes}</p>"
        )
    return "<h2>Example transformations</h2>" + "".join(blocks)


def _duplicates(result: RunResult) -> str:
    groups = [g for g in result.duplicate_groups if g["count"] > 1][:25]
    if not groups:
        return "<h2>Duplicate analysis</h2><p class='warn'>(no duplicate clusters)</p>"
    rows = "".join(
        f"<tr><td>{_esc(g['canonical'])}</td><td class='num'>{g['count']:,}</td>"
        f"<td class='num'>{len(g['variants'])}</td></tr>"
        for g in groups
    )
    return (
        "<h2>Duplicate analysis (top 25 clusters)</h2>"
        "<table><tr><th>Canonical URL</th><th class='num'>Duplicates</th>"
        f"<th class='num'>Variants kept</th></tr>{rows}</table>"
    )


def _largest(result: RunResult) -> str:
    if not result.stats.largest_urls:
        return ""
    rows = "".join(
        f"<tr><td class='num'>{length:,}</td><td>{_esc(url)}</td></tr>"
        for length, url in result.stats.largest_urls
    )
    return (
        "<h2>Largest URLs</h2><table><tr><th class='num'>Length</th><th>URL</th></tr>"
        f"{rows}</table>"
    )


def write(path: Path, result: RunResult) -> None:
    """Render the standalone HTML report."""
    stats = result.stats
    meta = result.metadata
    meta_rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{_esc(value)}</td></tr>"
        for key, value in meta.items()
        if key != "configuration"
    )
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{APP_TITLE} - Report</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{APP_TITLE}<small>{_esc(PRIMARY_TAGLINE)}</small></h1>
  <p class="tagline">URL Deduplicator &amp; Canonicalization Engine</p>
</header>

<h2>Summary</h2>
{_cards(stats)}

<h2>Processing report</h2>
<pre>{_esc(render_dashboard(stats))}</pre>

<h2>URL categories</h2>
{_top_table("Category counts", stats.categories, 50)}

{_top_table("Top hosts", stats.hosts, 10)}
{_top_table("Top domains", stats.domains, 10)}
{_top_table("Top extensions", stats.extensions, 10)}
{_top_table("Top parameters", stats.params, 10)}

{_largest(result)}
{_duplicates(result)}
{_examples(result)}

<h2>Error summary</h2>
{_top_table("Invalid URL reasons", stats.errors, 20)}

<h2>Run metadata (reproducibility)</h2>
<table><tr><th>Field</th><th>Value</th></tr>{meta_rows}</table>

<footer>
Generated by <strong>{APP_TITLE}</strong> &middot;
Author: <a href="{GITHUB_URL}">{_esc(AUTHOR)}</a> &middot;
<a href="{YOUTUBE_URL}">YouTube</a> &middot;
Classification is heuristic and based on URL structure only; no network
requests were made.
</footer>
</div>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
