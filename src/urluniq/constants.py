"""Constants, branding and enumerations shared across URLUNIQ."""

from __future__ import annotations

from enum import IntEnum, unique

__version__ = "2.0.0"

APP_NAME = "URLUNIQ"
APP_TITLE = "URLUNIQ 2.0"
APP_SUBTITLE = "URL Deduplicator & Canonicalization Engine"
AUTHOR = "mrdineshpathro-dot"
GITHUB_URL = "https://github.com/mrdineshpathro-dot"
YOUTUBE_URL = "https://www.youtube.com/@GithubHacker"

PRIMARY_TAGLINE = "Normalize. Canonicalize. Deduplicate. Analyze."
SECONDARY_TAGLINE = "Millions of URLs. One clean dataset."

BANNER = r"""
██╗   ██╗██████╗ ██╗         ██████╗ ███╗   ██╗██╗ ██████╗
██║   ██║██╔══██╗██║        ██╔═══██╗████╗  ██║██║██╔═══██╗
██║   ██║██████╔╝██║        ██║   ██║██╔██╗ ██║██║██║   ██║
██║   ██║██╔══██╗██║        ██║   ██║██╔╝██╗██║██║██║   ██║
╚██████╔╝██║  ██║███████╗   ╚██████╔╝██║ ╚████║██║╚██████╔╝
 ╚═════╝ ╚═╝  ╚═╝╚══════╝    ╚═════╝ ╚═╝  ╚═══╝╚═╝ ╚═════╝
"""

# Schemes URLUNIQ understands by default.  Everything else is reported as
# "invalid scheme".  Extend through the ``[validation]`` config section.
DEFAULT_ALLOWED_SCHEMES = frozenset({"http", "https", "ftp", "ftps", "ws", "wss"})

# Ports implied by the scheme: an explicitly written default port is noise.
DEFAULT_PORTS: dict[str, int] = {
    "http": 80,
    "https": 443,
    "ftp": 21,
    "ftps": 990,
    "ws": 80,
    "wss": 443,
}

PORT_MIN = 1
PORT_MAX = 65535

# RFC 3986 unreserved characters - percent-encoded forms of these may be
# safely decoded (``%7E`` -> ``~``).
UNRESERVED_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

# Raw characters that never need escaping inside a path component.
PATH_SAFE_RAW = UNRESERVED_CHARS | frozenset("!$&'()*+,;=:@/")

# Raw characters that never need escaping inside a query component.  Note the
# deliberate absence of ``&`` and ``=`` (parameter delimiters); ``+`` is kept
# raw because re-encoding it would change form-encoding semantics.
QUERY_SAFE_RAW = UNRESERVED_CHARS | frozenset("!'()*+%;:@/?")

# Last path segments that are equivalent to the directory itself.
DEFAULT_INDEX_FILES = frozenset(
    {
        "index.html",
        "index.htm",
        "index.php",
        "index.jsp",
        "index.aspx",
        "index.asp",
        "index.cgi",
        "default.html",
        "default.htm",
        "default.aspx",
        "default.asp",
    }
)

# Parameter name fragments that hint at session/state parameters.  Used for
# detection only - never for removal unless explicitly configured.
SESSION_PARAM_HINTS: tuple[str, ...] = (
    "session",
    "sess",
    "sid",
    "jsessionid",
    "phpsessid",
    "asp.net_sessionid",
    "token",
    "csrf",
    "xsrf",
    "auth",
    "ticket",
    "nonce",
    "state",
)

# Common second-level public suffixes used by the registrable-domain
# heuristic (a full Public Suffix List is intentionally avoided so URLUNIQ
# stays offline and dependency free).
SECOND_LEVEL_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "co.jp",
        "or.jp",
        "ne.jp",
        "co.in",
        "net.in",
        "org.in",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "com.br",
        "com.mx",
        "com.cn",
        "com.tw",
        "com.hk",
        "com.sg",
        "com.my",
        "co.za",
        "com.ar",
        "com.tr",
        "co.kr",
    }
)

# Reason labels used by the transformation explainer.
REASON_SCHEME_LOWERED = "scheme lowercased"
REASON_SCHEME_UPGRADED = "scheme upgraded to https"
REASON_HOST_LOWERED = "hostname lowercased"
REASON_IDN_ENCODED = "unicode hostname encoded to punycode (IDNA)"
REASON_DEFAULT_PORT_REMOVED = "default port removed"
REASON_PORT_NORMALIZED = "port normalized"
REASON_EMPTY_PATH = "empty path expanded to '/'"
REASON_TRAILING_SLASH_ADDED = "trailing slash added"
REASON_TRAILING_SLASH_REMOVED = "trailing slash removed"
REASON_DUP_SLASHES = "duplicate slashes collapsed"
REASON_DOT_SEGMENTS = "dot segments removed"
REASON_PERCENT_NORMALIZED = "percent-encoding normalized"
REASON_FRAGMENT_REMOVED = "fragment removed"
REASON_USERINFO_REDACTED = "credentials redacted"
REASON_WWW_STRIPPED = "'www.' prefix removed"
REASON_INDEX_STRIPPED = "default index document removed"
REASON_PARAMS_SORTED = "query parameters sorted"
REASON_DUP_PARAMS = "duplicate query parameters removed"
REASON_TRACKING_REMOVED = "tracking parameters removed"
REASON_EMPTY_PARAMS_REMOVED = "empty query parameters removed"
REASON_PARAM_DROPPED = "query parameter removed by rule"
REASON_PARAM_KEPT = "query parameter kept by rule"
REASON_IPV4_NORMALIZED = "IPv4 address normalized"
REASON_IPV6_NORMALIZED = "IPv6 address normalized"
REASON_URL_TRIMMED = "surrounding whitespace removed"
REASON_CONTROL_CHARS = "control characters removed"

# Error reasons for the invalid-URL dataset.
ERR_INVALID_SCHEME = "invalid scheme"
ERR_MALFORMED_HOST = "malformed hostname"
ERR_MALFORMED_PORT = "malformed port"
ERR_INVALID_STRUCTURE = "invalid URL structure"
ERR_UNSUPPORTED_FORMAT = "unsupported format"
ERR_EMPTY_URL = "empty URL"
ERR_URL_TOO_LONG = "URL exceeds maximum length"


@unique
class ExitCode(IntEnum):
    """Process exit codes.  Documented in README > CLI reference."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGUMENTS = 2
    INPUT_ERROR = 3
    OUTPUT_ERROR = 4
    CONFIG_ERROR = 5
