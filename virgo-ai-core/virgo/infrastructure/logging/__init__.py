"""Explicit structured logging foundation."""

from virgo.infrastructure.logging.formatters import (
    ConsoleFormatter,
    JsonLineFormatter,
    redact_sensitive_fields,
)
from virgo.infrastructure.logging.setup import LoggingRuntime, configure_logging

__all__ = (
    "ConsoleFormatter",
    "JsonLineFormatter",
    "LoggingRuntime",
    "configure_logging",
    "redact_sensitive_fields",
)
