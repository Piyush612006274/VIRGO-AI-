"""Presentation-only foundation content area."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

CONTENT_OBJECT_NAME = "foundationContent"
CONTENT_TEXT_OBJECT_NAME = "foundationContentText"


class ContentPlaceholderWidget(QFrame):
    """Display the authorized foundation-ready shell content."""

    def __init__(self, text: str = "Virgo AI foundation ready") -> None:
        super().__init__()
        self.setObjectName(CONTENT_OBJECT_NAME)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._text_label = QLabel(text)
        self._text_label.setObjectName(CONTENT_TEXT_OBJECT_NAME)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self._text_label)
        layout.addStretch()

    @property
    def text(self) -> str:
        """Return the visible foundation content."""
        return self._text_label.text()
