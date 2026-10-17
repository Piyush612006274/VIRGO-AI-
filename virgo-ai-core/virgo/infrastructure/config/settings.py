"""Immutable, validated application foundation settings."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from virgo.contracts.errors import ConfigurationError

DEFAULT_MAX_LOG_FILE_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ApplicationEnvironment(StrEnum):
    """Supported application runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Final validated settings after all configured sources are applied."""

    environment: ApplicationEnvironment = ApplicationEnvironment.DEVELOPMENT
    data_directory: Path = Path("data")
    logging_level: str = "INFO"
    logging_directory: Path = Path("data/runtime/logs")
    console_logging_enabled: bool = True
    file_logging_enabled: bool = False
    max_log_file_bytes: int = DEFAULT_MAX_LOG_FILE_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT

    def __post_init__(self) -> None:
        """Reject invalid settings with the canonical structured error."""
        if self.logging_level not in VALID_LOG_LEVELS:
            self._raise_invalid("logging_level", "must be a supported level")
        if self.max_log_file_bytes <= 0:
            self._raise_invalid("max_log_file_bytes", "must be greater than zero")
        if self.log_backup_count < 0:
            self._raise_invalid("log_backup_count", "must not be negative")
        if not str(self.data_directory).strip():
            self._raise_invalid("data_directory", "must not be empty")
        if not str(self.logging_directory).strip():
            self._raise_invalid("logging_directory", "must not be empty")

    def to_safe_dict(self) -> dict[str, str | bool | int]:
        """Return settings safe for diagnostics; this model contains no secrets."""
        return {
            "environment": self.environment.value,
            "data_directory": self.data_directory.as_posix(),
            "logging_level": self.logging_level,
            "logging_directory": self.logging_directory.as_posix(),
            "console_logging_enabled": self.console_logging_enabled,
            "file_logging_enabled": self.file_logging_enabled,
            "max_log_file_bytes": self.max_log_file_bytes,
            "log_backup_count": self.log_backup_count,
        }

    @staticmethod
    def _raise_invalid(field_name: str, reason: str) -> None:
        raise ConfigurationError(
            f"Invalid configuration field {field_name!r}: {reason}",
            user_safe_explanation="The application configuration is invalid.",
            source_module=__name__,
        )
