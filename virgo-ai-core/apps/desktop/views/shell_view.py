"""Composed presentation-only view for the desktop foundation."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from apps.desktop.themes.phase_two import PHASE_TWO_STYLE
from apps.desktop.views.stage_one import StageOneScreens
from apps.desktop.widgets import HeaderWidget, StatusBarWidget

SHELL_MARGIN = 14
SHELL_SPACING = 10


class ShellView(QWidget):
    """Compose exactly one header, content area, and status area."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appShell")
        self.header = HeaderWidget()
        self.content = StageOneScreens()
        self.status = StatusBarWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SHELL_MARGIN, SHELL_MARGIN, SHELL_MARGIN, SHELL_MARGIN
        )
        layout.setSpacing(SHELL_SPACING)
        layout.addWidget(self.header)
        layout.addWidget(self.content, stretch=1)
        layout.addWidget(self.status)
        self.setStyleSheet(PHASE_TWO_STYLE)
