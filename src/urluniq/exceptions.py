"""Exception hierarchy for URLUNIQ.

Every error carries the process exit code it maps to, so the CLI can fail
with meaningful status codes (see README "Exit codes").
"""

from __future__ import annotations

from urluniq.constants import ExitCode


class URLUNIQError(Exception):
    """Base class for all URLUNIQ errors."""

    exit_code: ExitCode = ExitCode.GENERAL_ERROR


class ConfigError(URLUNIQError):
    """Raised when a configuration file or profile is invalid."""

    exit_code = ExitCode.CONFIG_ERROR


class InputError(URLUNIQError):
    """Raised when input files cannot be read or parsed at the container level."""

    exit_code = ExitCode.INPUT_ERROR


class OutputError(URLUNIQError):
    """Raised when output files cannot be written."""

    exit_code = ExitCode.OUTPUT_ERROR


class URLValidationError(URLUNIQError):
    """Raised (library mode) when a URL fails validation."""

    exit_code = ExitCode.GENERAL_ERROR


class BackendError(URLUNIQError):
    """Raised by storage backends (e.g. SQLite failures)."""

    exit_code = ExitCode.GENERAL_ERROR


class PluginError(URLUNIQError):
    """Raised when a plugin fails to load or register."""

    exit_code = ExitCode.GENERAL_ERROR
