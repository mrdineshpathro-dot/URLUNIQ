"""Example plugin: extra tracking parameters + an affiliate classifier.

Enabled only when ``[plugins] example_tracking = true`` (or
``example_classifier = true``) in the configuration, so the default
behaviour of URLUNIQ is unchanged.  Use it as a template for your own
plugins - see the package docstring for the full registry API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from urluniq.config.loader import Config
from urluniq.models import URLRecord

if TYPE_CHECKING:  # pragma: no cover
    from urluniq.plugins import PluginRegistry

# Additional tracking parameters this plugin knows about.
EXTRA_TRACKING = (
    "spm_idz",
    "scid",
    "aff_id",
    "affiliate",
    "campaign_id",
    "mc_cid",
    "rr_publisher",
)

_AFFILIATE_MARKERS = ("/ref=", "affiliate", "/aff/", "partners/", "refer/")


def register(registry: PluginRegistry, config: Config | None = None) -> None:
    """Called by the plugin loader; activates parts gated by config flags."""
    if config is None:
        config = Config()

    if config.plugins.example_tracking:
        registry.register_tracking_param(*EXTRA_TRACKING)

    if config.plugins.example_classifier:

        def affiliate_classifier(record: URLRecord) -> str | None:
            url = record.raw.lower()
            if any(marker in url for marker in _AFFILIATE_MARKERS):
                return "static"
            return None

        registry.register_classifier(affiliate_classifier)
