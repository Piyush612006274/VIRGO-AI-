"""Explicit configuration loading with defaults, JSON, then environment precedence."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Never

from virgo.contracts.errors import ConfigurationError
from virgo.infrastructure.config.settings import ApplicationEnvironment, AppSettings

ENVIRONMENT_PREFIX: Final = "VIRGO_"
SETTING_NAMES: Final = frozenset(
    {
        "environment",
        "data_directory",
        "logging_level",
        "logging_directory",
        "console_logging_enabled",
        "file_logging_enabled",
        "max_log_file_bytes",
        "log_backup_count",
    }
)
ENVIRONMENT_NAMES: Final = {
    f"{ENVIRONMENT_PREFIX}{name.upper()}": name for name in SETTING_NAMES
}


def load_settings(
    config_file: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> AppSettings:
    """Load settings using Defaults → JSON file → environment precedence."""
    values: dict[str, object] = {}
    if config_file is not None:
        values.update(_load_json_file(config_file))
    environment_values = os.environ if environment is None else environment
    values.update(_load_environment(environment_values))
    return _build_settings(values)


def _load_json_file(config_file: Path) -> dict[str, object]:
    try:
        with config_file.open(encoding="utf-8") as file_handle:
            loaded: object = json.load(file_handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(
            f"Unable to load configuration file {config_file}",
            technical_detail=str(error),
            user_safe_explanation="The configuration file could not be loaded.",
            source_module=__name__,
            cause=error,
        ) from error
    if not isinstance(loaded, dict):
        _raise_invalid("configuration file root must be a JSON object")
    unknown = set(loaded) - SETTING_NAMES
    if unknown:
        _raise_invalid(f"unknown configuration keys: {', '.join(sorted(unknown))}")
    return {str(key): value for key, value in loaded.items()}


def _load_environment(environment: Mapping[str, str]) -> dict[str, object]:
    values: dict[str, object] = {}
    for environment_name, setting_name in ENVIRONMENT_NAMES.items():
        if environment_name in environment:
            values[setting_name] = environment[environment_name]
    return values


def _build_settings(values: Mapping[str, object]) -> AppSettings:
    try:
        return AppSettings(
            environment=_parse_environment(values.get("environment", "development")),
            data_directory=_parse_path(
                values.get("data_directory", "data"), "data_directory"
            ),
            logging_level=_parse_string(
                values.get("logging_level", "INFO"), "logging_level"
            ).upper(),
            logging_directory=_parse_path(
                values.get("logging_directory", "data/runtime/logs"),
                "logging_directory",
            ),
            console_logging_enabled=_parse_bool(
                values.get("console_logging_enabled", True),
                "console_logging_enabled",
            ),
            file_logging_enabled=_parse_bool(
                values.get("file_logging_enabled", False),
                "file_logging_enabled",
            ),
            max_log_file_bytes=_parse_int(
                values.get("max_log_file_bytes", 10 * 1024 * 1024),
                "max_log_file_bytes",
            ),
            log_backup_count=_parse_int(
                values.get("log_backup_count", 5), "log_backup_count"
            ),
        )
    except ConfigurationError:
        raise
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "Configuration values could not be validated",
            technical_detail=str(error),
            source_module=__name__,
            cause=error,
        ) from error


def _parse_environment(value: object) -> ApplicationEnvironment:
    text = _parse_string(value, "environment").lower()
    try:
        return ApplicationEnvironment(text)
    except ValueError as error:
        raise ConfigurationError(
            f"Invalid application environment: {text!r}",
            source_module=__name__,
            cause=error,
        ) from error


def _parse_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_invalid(f"{field_name} must be a non-empty string")
    return value.strip()


def _parse_path(value: object, field_name: str) -> Path:
    return Path(_parse_string(value, field_name))


def _parse_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    _raise_invalid(f"{field_name} must be a boolean")


def _parse_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        _raise_invalid(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    _raise_invalid(f"{field_name} must be an integer")


def _raise_invalid(message: str) -> Never:
    raise ConfigurationError(message, source_module=__name__)
