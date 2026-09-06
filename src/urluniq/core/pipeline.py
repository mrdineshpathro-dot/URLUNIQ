"""Per-URL processing pipeline.

Stages: Parsing -> Validation -> Normalization -> Canonicalization ->
Filtering -> Classification -> (Feature extraction).

The pipeline is a pure function of ``(config, raw_url)`` which makes every
stage independently testable and safe to run inside worker processes.
"""

from __future__ import annotations

from dataclasses import dataclass

from urluniq.classifiers.classifier import URLClassifier
from urluniq.config.loader import Config
from urluniq.constants import DEFAULT_PORTS
from urluniq.core.parser import (
    build_features,
    parse_url,
    path_depth,
    path_extension,
    registrable_domain,
    subdomain_of,
)
from urluniq.core.validator import Validator
from urluniq.filters.engine import FilterEngine
from urluniq.models import Profile, URLRecord
from urluniq.normalizers import build_canonicalizer, build_normalizer


@dataclass(slots=True)
class PipelineOptions:
    """Toggles applied on top of the configuration."""

    classify: bool = True
    extract_features: bool = False
    redact_userinfo: bool = False


def _default_port(scheme: str) -> int:
    """Effective port for a scheme when no explicit port remains."""
    return DEFAULT_PORTS.get(scheme, 80)


class URLPipeline:
    """Stateless (per-config) URL processing pipeline."""

    def __init__(
        self,
        config: Config,
        profile: Profile | str | None = None,
        options: PipelineOptions | None = None,
        classifier: URLClassifier | None = None,
        cache_size: int | None = None,
    ) -> None:
        self.config = config
        self.profile = Profile(profile) if profile else config.profile
        self.options = options or PipelineOptions()
        self.validator = Validator(
            allowed_schemes=frozenset(config.validation.allowed_schemes),
            max_url_length=config.validation.max_url_length,
        )
        self.normalizer = build_normalizer(
            self.profile, config, redact_userinfo=self.options.redact_userinfo
        )
        self.canonicalizer = build_canonicalizer(
            config, profile=self.profile, redact_userinfo=self.options.redact_userinfo
        )
        self.classifier = classifier or URLClassifier(config.extension_map())
        self.filter_engine = FilterEngine(config)
        # Per-run caches (never global state).  Duplicate-heavy recon datasets
        # hit these constantly; unique-heavy datasets only pay a dict insert.
        self._cache_limit = (
            cache_size if cache_size is not None else config.performance.process_cache_size
        )
        self._record_cache: dict[str, URLRecord] = {}
        self._domain_cache: dict[str, tuple[str, str]] = {}

    # ------------------------------------------------------------------

    def process(self, raw: str) -> URLRecord:
        """Run one raw URL string through every pipeline stage."""
        cached = self._record_cache.get(raw)
        if cached is not None:
            return cached
        record = self._process_uncached(raw)
        if len(self._record_cache) < self._cache_limit:
            self._record_cache[raw] = record
        return record

    def _process_uncached(self, raw: str) -> URLRecord:
        record = URLRecord(raw=raw)
        parsed, error, cleanup = parse_url(raw, self.config.validation.max_url_length)
        record.reasons.extend(cleanup)

        if parsed is None:
            record.error = error or "invalid URL structure"
            return record

        validation_error = self.validator.validate(parsed)
        if validation_error:
            record.error = validation_error
            return record

        normalized = self.normalizer.apply(parsed)
        canonical = self.canonicalizer.apply(parsed)
        record.normalized = normalized.url
        record.canonical = canonical.url
        record.reasons.extend(normalized.reasons)
        record.tracking_removed = normalized.tracking_removed

        # Snapshot the normalized components directly from the normalizer
        # results (no second URL parse needed).
        record.scheme = normalized.scheme
        record.host = normalized.host.lower()
        record.port = (
            normalized.port if normalized.port is not None else _default_port(normalized.scheme)
        )
        record.path = normalized.path
        record.query = normalized.query
        record.extension = path_extension(normalized.path)
        record.param_names = normalized.param_names
        record.param_count = len(normalized.param_names)
        record.has_fragment = bool(parsed.fragment)
        record.has_userinfo = parsed.has_userinfo
        record.url_length = len(record.raw)
        record.path_depth = path_depth(normalized.path)
        domain, subdomain = self._domain_parts(record.host)
        record.registrable_domain = domain
        record.subdomain = subdomain

        if self.options.classify:
            record.category = self.classifier.classify(record).label

        kept, drop_reason = self.filter_engine.keep(record)
        if not kept:
            record.dropped = True
            record.drop_reason = drop_reason
            return record

        if self.options.extract_features:
            record.features = build_features(record, parsed).to_dict()
        return record

    def _domain_parts(self, host: str) -> tuple[str, str]:
        cached = self._domain_cache.get(host)
        if cached is None:
            cached = (registrable_domain(host), subdomain_of(host))
            self._domain_cache[host] = cached
        return cached
