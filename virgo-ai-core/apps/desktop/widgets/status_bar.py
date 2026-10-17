"""Presentation-only bottom status area."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

STATUS_OBJECT_NAME = "applicationStatus"
STATUS_INDICATOR_OBJECT_NAME = "applicationStatusIndicator"
STATUS_TEXT_OBJECT_NAME = "applicationStatusText"


class StatusBarWidget(QWidget):
    """Display a concise shell status without owning application state."""

    def __init__(self, status_text: str = "Ready") -> None:
        super().__init__()
        self.setObjectName(STATUS_OBJECT_NAME)

        self._state_indicator = QLabel("●")
        self._state_indicator.setObjectName(STATUS_INDICATOR_OBJECT_NAME)
        self._state_indicator.setProperty("applicationState", "idle")
        self._state_indicator.setAccessibleName("Application state: idle")

        self._status_label = QLabel(status_text)
        self._status_label.setObjectName(STATUS_TEXT_OBJECT_NAME)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._state_indicator)
        layout.addWidget(self._status_label)

    @property
    def status_text(self) -> str:
        """Return the visible presentation status."""
        return self._status_label.text()

    def set_status_text(self, status_text: str) -> None:
        """Replace the visible presentation text."""
        self._status_label.setText(status_text)

    @property
    def visual_state(self) -> str:
        """Return the presentation-only state indicator value."""
        return str(self._state_indicator.property("applicationState"))

    def set_visual_state(self, state_name: str) -> None:
        """Update the simple accessible state indicator."""
        self._state_indicator.setProperty("applicationState", state_name)
        self._state_indicator.setAccessibleName(f"Application state: {state_name}")
