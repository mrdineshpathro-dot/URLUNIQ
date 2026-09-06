"""Heuristic URL classification rules.

Classification is *heuristic only* and clearly labelled as such: URLUNIQ
never fetches URLs, so categories derive purely from path/query/extension
shape.  Rules are evaluated in priority order; the first match wins.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical category keys and their display labels.
CATEGORY_LABELS: dict[str, str] = {
    "auth": "Auth",
    "logout": "Logout",
    "upload": "Upload",
    "download": "Download",
    "redirect": "Redirect",
    "search": "Search",
    "api": "API",
    "js": "JS",
    "css": "CSS",
    "image": "Image",
    "document": "Document",
    "static": "Static",
    "html": "HTML",
    "parameterized": "Parameterized",
    "extensionless": "Extensionless",
    "unknown": "Unknown",
}

# Categories produced by extensions.txt rather than keywords.
EXTENSION_CATEGORIES = {"js", "css", "image", "document", "static", "html", "api"}


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    """One heuristic rule: keyword / parameter / extension signals."""

    category: str
    path_keywords: tuple[str, ...] = ()
    param_names: tuple[str, ...] = ()
    note: str = ""


# Evaluated top to bottom; first match wins.
DEFAULT_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        "logout",
        path_keywords=("logout", "log-out", "signout", "sign-out", "sign_off"),
        note="logout keyword in path",
    ),
    ClassificationRule(
        "auth",
        path_keywords=(
            "login",
            "log-in",
            "signin",
            "sign-in",
            "signup",
            "sign-up",
            "register",
            "auth",
            "sso",
            "oauth",
            "authenticate",
            "verification",
            "verify",
            "password",
        ),
        note="authentication keyword in path",
    ),
    ClassificationRule(
        "upload",
        path_keywords=("upload", "attach", "post/new", "media/new"),
        note="upload keyword in path",
    ),
    ClassificationRule(
        "download",
        path_keywords=("download", "dl/", "export", "getfile", "attachment"),
        note="download keyword in path",
    ),
    ClassificationRule(
        "redirect",
        param_names=(
            "url",
            "next",
            "redirect",
            "redirect_uri",
            "redirect_url",
            "return",
            "returnurl",
            "return_to",
            "goto",
            "continue",
            "target",
            "dest",
            "destination",
            "r",
            "u",
        ),
        note="open-redirect-style parameter present",
    ),
    ClassificationRule(
        "search",
        path_keywords=("search", "query", "find", "results"),
        param_names=("q", "query", "s", "search", "kw", "keyword", "term"),
        note="search path or query parameter",
    ),
    ClassificationRule(
        "api",
        path_keywords=(
            "/api",
            "api.",
            "/graphql",
            "/rpc",
            "/rest",
            "/soap",
            "/webservice",
            "/v1",
            "/v2",
            "/v3",
        ),
        note="API-looking path",
    ),
)

# Extension fallback order when no keyword rule matched.
EXTENSION_RULE_ORDER: tuple[str, ...] = (
    "api",  # e.g. .json / .graphql via extensions map
    "js",
    "css",
    "image",
    "document",
    "static",
    "html",
)
