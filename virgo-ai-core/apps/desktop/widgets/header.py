"""Presentation-only application header."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

HEADER_OBJECT_NAME = "applicationHeader"
TITLE_OBJECT_NAME = "applicationTitle"


class HeaderWidget(QWidget):
    """Display the Virgo AI application identity."""

    def __init__(self, title: str = "Virgo AI") -> None:
        super().__init__()
        self.setObjectName(HEADER_OBJECT_NAME)

        self._title_label = QLabel(title)
        self._title_label.setObjectName(TITLE_OBJECT_NAME)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title_label)
        tagline = QLabel("Voice First. You speak, Virgo handles the rest.")
        tagline.setObjectName("headerTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline, 1)

    @property
    def title(self) -> str:
        """Return the visible application title."""
        return self._title_label.text()
