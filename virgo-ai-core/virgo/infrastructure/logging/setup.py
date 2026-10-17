"""Explicit, idempotent standard-library logging setup and cleanup."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from virgo.contracts.errors import ConfigurationError
from virgo.infrastructure.config import AppSettings
from virgo.infrastructure.logging.formatters import ConsoleFormatter, JsonLineFormatter

CONSOLE_HANDLER_NAME = "virgo.console"
FILE_HANDLER_NAME = "virgo.file"
DEFAULT_LOG_FILE_NAME = "virgo.log"


class LoggingRuntime:
    """Own and explicitly clean up handlers installed by Virgo."""

    def __init__(
        self, logger: logging.Logger, handlers: tuple[logging.Handler, ...]
    ) -> None:
        self.logger = logger
        self._handlers = handlers

    def shutdown(self) -> None:
        """Remove and close only the handlers owned by this runtime."""
        for handler in self._handlers:
            self.logger.removeHandler(handler)
            handler.close()
        self._handlers = ()


def configure_logging(
    settings: AppSettings,
    *,
    logger: logging.Logger | None = None,
) -> LoggingRuntime:
    """Configure Virgo logging explicitly and without duplicate handlers."""
    target_logger = logging.getLogger("virgo") if logger is None else logger
    _remove_managed_handlers(target_logger)
    handlers: list[logging.Handler] = []
    try:
        if settings.console_logging_enabled:
            console_handler = logging.StreamHandler()
            console_handler.set_name(CONSOLE_HANDLER_NAME)
            console_handler.setFormatter(ConsoleFormatter())
            handlers.append(console_handler)
        if settings.file_logging_enabled:
            handlers.append(_create_file_handler(settings))
    except (OSError, ValueError) as error:
        for handler in handlers:
            handler.close()
        raise ConfigurationError(
            "Unable to configure logging",
            technical_detail=str(error),
            user_safe_explanation="Logging could not be configured.",
            source_module=__name__,
            cause=error,
        ) from error

    target_logger.setLevel(settings.logging_level)
    target_logger.propagate = False
    for handler in handlers:
        handler.setLevel(settings.logging_level)
        target_logger.addHandler(handler)
    return LoggingRuntime(target_logger, tuple(handlers))


def _create_file_handler(settings: AppSettings) -> RotatingFileHandler:
    logging_directory = Path(settings.logging_directory)
    logging_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logging_directory / DEFAULT_LOG_FILE_NAME,
        maxBytes=settings.max_log_file_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.set_name(FILE_HANDLER_NAME)
    handler.setFormatter(JsonLineFormatter())
    return handler


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in tuple(logger.handlers):
        if handler.get_name() in {CONSOLE_HANDLER_NAME, FILE_HANDLER_NAME}:
            logger.removeHandler(handler)
            handler.close()
