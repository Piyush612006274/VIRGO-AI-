"""Presentation-only components for the Phase 2 desktop shell."""

from dataclasses import dataclass

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from apps.desktop.themes.phase_two import AMBER, CYAN, GREEN, RED, VIOLET


@dataclass(frozen=True, slots=True)
class CoreStatePresentation:
    label: str
    color: str
    motion: str


CORE_STATES = {
    "idle": CoreStatePresentation("Ready", CYAN, "breathe"),
    "listening": CoreStatePresentation("Listening", CYAN, "pulse"),
    "processing_speech": CoreStatePresentation("Understanding", CYAN, "focus"),
    "thinking": CoreStatePresentation("Thinking", VIOLET, "orbit"),
    "planning": CoreStatePresentation("Planning", VIOLET, "orbit"),
    "researching": CoreStatePresentation("Researching", CYAN, "scan"),
    "working": CoreStatePresentation("Working", CYAN, "orbit"),
    "verifying": CoreStatePresentation("Verifying", GREEN, "focus"),
    "waiting_for_permission": CoreStatePresentation(
        "Waiting for permission", AMBER, "still"
    ),
    "responding": CoreStatePresentation("Responding", VIOLET, "orbit"),
    "speaking": CoreStatePresentation("Speaking", CYAN, "pulse"),
    "interrupted": CoreStatePresentation("Interrupted", AMBER, "settle"),
    "recovering": CoreStatePresentation("Recovering", GREEN, "orbit"),
    "offline": CoreStatePresentation("Offline", "#607189", "still"),
    "error": CoreStatePresentation("Needs attention", RED, "pulse"),
}


class VirgoCoreWidget(QFrame):
    """Paint a lightweight state orb; application behavior remains elsewhere."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("virgoCore")
        self.setMinimumSize(220, 220)
        self._state = CORE_STATES["idle"]
        self._reduced_motion = False
        self._phase = 0.0
        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(700)
        self._animation.setStartValue(0.55)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)
        self.set_state("idle")

    def _get_phase(self) -> float:
        return self._phase

    def _set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    @property
    def presentation_state(self) -> str:
        return self._state.label

    @property
    def reduced_motion(self) -> bool:
        return self._reduced_motion

    @property
    def animation_running(self) -> bool:
        return self._animation.state() == QPropertyAnimation.State.Running

    def set_reduced_motion(self, reduced: bool) -> None:
        self._reduced_motion = reduced
        self._animation.stop()
        if not reduced and self._state.motion != "still":
            self._animation.start()

    def set_state(self, state_name: str) -> None:
        self._state = CORE_STATES.get(state_name, CORE_STATES["idle"])
        self.setAccessibleName(f"Virgo Core: {self._state.label}")
        self._animation.stop()
        if not self._reduced_motion and self._state.motion != "still":
            self._animation.start()
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        base = max(36, min(self.width(), self.height()) // 4)
        radius = round(base * (1.0 + 0.04 * self._phase))
        color = QColor(self._state.color)
        for offset, alpha in ((28, 35), (14, 70)):
            ring = QColor(color)
            ring.setAlpha(alpha)
            painter.setPen(QPen(ring, 2))
            painter.drawEllipse(center, radius + offset, radius + offset)
        painter.setBrush(color)
        painter.setPen(QPen(color.lighter(150), 2))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(QColor("#07101c"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._state.label)


class ActivityRail(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("activityRail")
        self.setAccessibleName("Live activity")
        self.summary = QLabel("Virgo is ready")
        self.summary.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.timeline = QListWidget()
        self.timeline.setAccessibleName("Activity timeline")
        self.timeline.addItem("Ready — waiting for a request")
        layout = QVBoxLayout(self)
        title = QLabel("Live activity")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(self.summary)
        layout.addWidget(self.progress)
        layout.addWidget(self.timeline, 1)

    def present_state(self, state: str, message: str) -> None:
        self.summary.setText(message)
        self.progress.setVisible(
            state not in {"idle", "error", "interrupted", "offline"}
        )
        entry = f"{state.replace('_', ' ').title()} — {message}"
        if self.timeline.item(self.timeline.count() - 1).text() != entry:
            self.timeline.addItem(entry)
            self.timeline.scrollToBottom()


class NavigationRail(QFrame):
    def __init__(self, names: tuple[str, ...], on_select: object) -> None:
        super().__init__()
        self.setObjectName("navigationRail")
        self.setAccessibleName("Workspace navigation")
        self.setMinimumWidth(208)
        self.setMaximumWidth(236)
        self.buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        brand_row = QHBoxLayout()
        brand = QLabel("✦  Virgo AI")
        brand.setObjectName("brandLabel")
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)

        state = QLabel("●  All systems healthy")
        state.setObjectName("railStatus")
        layout.addWidget(state)

        primary = ("Home", "Conversation")
        secondary = tuple(name for name in names if name not in {"Home", "Conversation", "Onboarding"})
        for group_index, group in enumerate((primary, secondary)):
            for name in group:
                label = "Task context" if name == "Personal AI" else name
                button = QPushButton(label)
                button.setCheckable(True)
                button.setAccessibleName(f"Open {name} workspace")
                button.clicked.connect(lambda checked=False, value=name: on_select(value))  # type: ignore[union-attr]
                self.buttons[name] = button
                layout.addWidget(button)
            if group_index == 0:
                divider = QLabel("WORKSPACE")
                divider.setObjectName("railSection")
                layout.addSpacing(4)
                layout.addWidget(divider)

        layout.addStretch(1)

    def select(self, name: str) -> None:
        for key, button in self.buttons.items():
            button.setChecked(key == name or (name == "Home" and key == "Conversation"))


class WorkflowStepper(QFrame):
    def __init__(self, stages: tuple[str, ...]) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.setAccessibleName("Workflow stages")
        grid = QGridLayout(self)
        for index, stage in enumerate(stages):
            label = QLabel(f"{index + 1}  {stage}")
            label.setWordWrap(True)
            label.setAccessibleName(f"Workflow stage {index + 1}: {stage}")
            grid.addWidget(label, index // 4, index % 4)
