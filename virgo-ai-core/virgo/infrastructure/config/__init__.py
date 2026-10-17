"""Explicit typed configuration foundation."""

from virgo.infrastructure.config.loader import load_settings
from virgo.infrastructure.config.settings import ApplicationEnvironment, AppSettings

__all__ = ("AppSettings", "ApplicationEnvironment", "load_settings")
