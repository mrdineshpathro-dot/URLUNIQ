"""Exclusion / filtering engine.

All filters are passive: they only decide whether a URL stays in the
dataset.  Regex filtering is explicit and opt-in (``--include-regex`` /
``--exclude-regex``).  Nothing here touches the network.
"""

from __future__ import annotations

import re

from urluniq.config.loader import Config
from urluniq.exceptions import ConfigError
from urluniq.models import URLRecord


class FilterEngine:
    """Applies include/exclude filters and the domain scope to records."""

    def __init__(
        self,
        config: Config,
        include_host: list[str] | None = None,
        exclude_host: list[str] | None = None,
        include_extension: list[str] | None = None,
        exclude_extension: list[str] | None = None,
        include_path: list[str] | None = None,
        exclude_path: list[str] | None = None,
        include_regex: list[str] | None = None,
        exclude_regex: list[str] | None = None,
        domain: str | None = None,
        include_subdomains: bool | None = None,
    ) -> None:
        f = config.filters
        self.include_host = _host_set(include_host if include_host is not None else f.include_host)
        self.exclude_host = _host_set(exclude_host if exclude_host is not None else f.exclude_host)
        self.include_ext = _ext_set(
            include_extension if include_extension is not None else f.include_extension
        )
        self.exclude_ext = _ext_set(
            exclude_extension if exclude_extension is not None else f.exclude_extension
        )
        self.include_path = list(include_path) if include_path is not None else list(f.include_path)
        self.exclude_path = list(exclude_path) if exclude_path is not None else list(f.exclude_path)
        self.domain = (domain or f.domain or "").lower().strip()
        self.include_subdomains = (
            f.include_subdomains if include_subdomains is None else include_subdomains
        )
        try:
            self.include_re = [
                re.compile(p)
                for p in (include_regex if include_regex is not None else f.include_regex)
            ]
            self.exclude_re = [
                re.compile(p)
                for p in (exclude_regex if exclude_regex is not None else f.exclude_regex)
            ]
        except re.error as exc:
            raise ConfigError(f"invalid filter regex: {exc}") from exc

    # ------------------------------------------------------------------

    def keep(self, record: URLRecord) -> tuple[bool, str]:
        """Return ``(kept, reason)`` for one record."""
        host = record.host.lower()
        ext = record.extension
        url = record.raw

        if self.domain and not self._in_domain(host):
            return False, f"outside domain scope {self.domain}"
        if self.include_host and not self._host_matches(host, self.include_host):
            return False, "host not in include-host list"
        if self.exclude_host and self._host_matches(host, self.exclude_host):
            return False, "host excluded"
        if self.include_ext and ext not in self.include_ext:
            return False, "extension not in include-extension list"
        if self.exclude_ext and ext in self.exclude_ext:
            return False, "extension excluded"
        for needle in self.include_path:
            if needle.lower() in (record.path or "").lower():
                break
        else:
            if self.include_path:
                return False, "path not in include-path list"
        for needle in self.exclude_path:
            if needle.lower() in (record.path or "").lower():
                return False, "path excluded"
        for pattern in self.include_re:
            if pattern.search(url):
                break
        else:
            if self.include_re:
                return False, "include-regex did not match"
        for pattern in self.exclude_re:
            if pattern.search(url):
                return False, "exclude-regex matched"
        return True, ""

    def _in_domain(self, host: str) -> bool:
        if host == self.domain:
            return True
        return self.include_subdomains and host.endswith("." + self.domain)

    @staticmethod
    def _host_matches(host: str, candidates: set[str]) -> bool:
        return host in candidates or any(host.endswith("." + c) or host == c for c in candidates)


def _host_set(values: list[str]) -> set[str]:
    return {v.lower().strip() for v in values if v.strip()}


def _ext_set(values: list[str]) -> set[str]:
    return {v.lower().strip().lstrip(".") for v in values if v.strip()}
