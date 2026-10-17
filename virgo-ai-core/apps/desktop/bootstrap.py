"""Explicit, side-effect-free desktop application bootstrap."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from apps.desktop.windows.main_window import VirgoMainWindow
from virgo.contracts.errors import UnknownInternalError, VirgoError
from virgo.infrastructure.config import load_settings
from virgo.infrastructure.logging import LoggingRuntime, configure_logging


def run(
    arguments: Sequence[str] | None = None,
    *,
    config_file: Path | None = None,
) -> int:
    """Start the minimal desktop shell and return its controlled exit code."""
    logging_runtime: LoggingRuntime | None = None
    window: VirgoMainWindow | None = None
    try:
        settings = load_settings(config_file)
        logging_runtime = configure_logging(settings)
        application = _get_or_create_application(arguments)
        window = VirgoMainWindow(settings)
        window.show()
        if window.controller is not None:
            QTimer.singleShot(0, window.controller.start)
        return application.exec()
    except VirgoError:
        _log_startup_failure(logging_runtime)
        raise
    except Exception as error:
        _log_startup_failure(logging_runtime)
        raise UnknownInternalError(
            "Desktop application startup failed",
            technical_detail=str(error),
            user_safe_explanation="Virgo AI could not start safely.",
            source_module=__name__,
            cause=error,
        ) from error
    finally:
        if window is not None and window.controller is not None:
            window.controller.close()
        if logging_runtime is not None:
            logging_runtime.shutdown()


def _get_or_create_application(arguments: Sequence[str] | None) -> QApplication:
    existing_application = QApplication.instance()
    if isinstance(existing_application, QApplication):
        return existing_application
    if existing_application is not None:
        raise RuntimeError("A non-GUI Qt application already exists")
    application_arguments = list(sys.argv if arguments is None else arguments)
    return QApplication(application_arguments)


def _log_startup_failure(logging_runtime: LoggingRuntime | None) -> None:
    if logging_runtime is not None:
        logging_runtime.logger.exception("Desktop application startup failed")
