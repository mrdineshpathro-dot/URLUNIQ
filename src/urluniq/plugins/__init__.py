"""Plugin architecture for URLUNIQ.

Plugins are plain Python modules inside ``urluniq/plugins`` that define a
``register(registry)`` function.  Through the registry they may add:

* tracking parameters
* classifier rules (callables receiving a :class:`~urluniq.models.URLRecord`)
* filters (callables receiving a record, returning ``(kept, reason)``)
* exporters (name -> writer factory) registered for structured output

Plugins are *passive*: URLUNIQ never executes external commands or network
calls on behalf of a plugin, and plugin modules are only imported - never
evaluated with untrusted data at import time beyond module-level constants.

Add a plugin by dropping ``my_plugin.py`` into this package; it is picked up
automatically unless ``[plugins] enabled = false`` in the configuration.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field

from urluniq.config.loader import Config
from urluniq.exceptions import PluginError
from urluniq.models import URLRecord

logger = logging.getLogger(__name__)

# A filter plugin: (record) -> (kept: bool, reason: str)
FilterRule = Callable[[URLRecord], "tuple[bool, str]"]
# A classifier plugin: (record) -> category key or None
ClassifierRule = Callable[[URLRecord], "str | None"]


@dataclass
class PluginRegistry:
    """Registry populated by plugin modules at load time."""

    tracking_params: set[str] = field(default_factory=set)
    classifier_rules: list[ClassifierRule] = field(default_factory=list)
    filter_rules: list[FilterRule] = field(default_factory=list)
    exporters: dict[str, Callable[..., object]] = field(default_factory=dict)
    loaded_plugins: list[str] = field(default_factory=list)

    def register_tracking_param(self, *names: str) -> None:
        self.tracking_params.update(n.lower() for n in names)

    def register_classifier(self, rule: ClassifierRule) -> None:
        self.classifier_rules.append(rule)

    def register_filter(self, rule: FilterRule) -> None:
        self.filter_rules.append(rule)

    def register_exporter(self, name: str, factory: Callable[..., object]) -> None:
        self.exporters[name] = factory


def load_plugins(enabled: bool = True, config: Config | None = None) -> PluginRegistry:
    """Import every plugin module in this package and collect registrations."""
    registry = PluginRegistry()
    if not enabled:
        return registry
    package = __name__
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_") or module_info.name == "base":
            continue
        module_name = f"{package}.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - plugins must not kill the app
            raise PluginError(f"plugin {module_name} failed to import: {exc}") from exc
        register = getattr(module, "register", None)
        if callable(register):
            try:
                if config is not None and len(inspect.signature(register).parameters) >= 2:
                    register(registry, config)
                else:
                    register(registry)
            except Exception as exc:  # noqa: BLE001
                raise PluginError(f"plugin {module_name} failed to register: {exc}") from exc
            registry.loaded_plugins.append(module_info.name)
            logger.debug("loaded plugin: %s", module_name)
    return registry
