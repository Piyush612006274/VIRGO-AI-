"""Original Stage 1 desktop window with injected application composition."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

from apps.desktop.views import ShellView
from virgo.infrastructure.config import AppSettings

if TYPE_CHECKING:
    from apps.desktop.controller import DesktopApplicationController


class VirgoMainWindow(QMainWindow):
    """Own the shell and one optional application controller."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        controller_factory: Callable[..., DesktopApplicationController] | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Virgo AI")
        self.resize(1460, 900)
        self.setMinimumSize(1120, 720)

        self.shell_view = ShellView()
        self.setCentralWidget(self.shell_view)
        self.controller: Any = None
        if settings is not None:
            if controller_factory is None:
                from apps.desktop.controller import DesktopApplicationController

                controller_factory = DesktopApplicationController
            self.controller = controller_factory(
                self.shell_view.content,
                self.shell_view.status,
                settings,
            )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.controller is not None:
            self.controller.close()
        super().closeEvent(event)
