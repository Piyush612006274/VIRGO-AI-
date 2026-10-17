"""Lightweight presentation-only Stage 1 desktop surfaces."""

from collections.abc import Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.widgets.phase_two import (
    ActivityRail,
    NavigationRail,
    VirgoCoreWidget,
    WorkflowStepper,
)


class _LabeledView(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("screenTitle")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        detail = QLabel(description)
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)
        self.content_layout = layout


class OnboardingView(_LabeledView):
    def __init__(self) -> None:
        super().__init__(
            "Welcome to Virgo AI",
            "Local-first setup keeps providers and personal data under your control.",
        )
        self.readiness = QListWidget()
        self.continue_button = QPushButton("Continue to Conversation")
        self.content_layout.addWidget(self.readiness, stretch=1)
        self.content_layout.addWidget(self.continue_button)

    def set_readiness(self, results: Iterable[tuple[str, str]]) -> None:
        self.readiness.clear()
        self.readiness.addItems([f"{name}: {status}" for name, status in results])


class ConversationView(QWidget):
    """Premium voice-first dashboard while preserving the controller-facing API."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("voiceFirstDashboard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Controller-facing widgets remain real interactive controls.
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("conversationTranscript")
        self.transcript.setPlaceholderText("Your conversation will appear here")
        self.transcript.setMinimumHeight(54)
        self.transcript.setMaximumHeight(118)

        self.text_input = QLineEdit()
        self.text_input.setObjectName("conversationInput")
        self.text_input.setPlaceholderText("Type a message (optional)")
        self.send = QPushButton("➤")
        self.send.setObjectName("sendButton")
        self.send.setAccessibleName("Send message")

        self.voice_mode = QCheckBox("Voice Mode")
        self.voice_mode.setObjectName("modePill")
        self.voice_mode.setAccessibleName("Keep voice conversation active")

        self.push_to_talk = QPushButton("Push-to-talk")
        self.push_to_talk.setObjectName("modePill")
        self.push_to_talk.setAccessibleName("Hold to speak")

        self.stop = QPushButton("Stop Response")
        self.stop.setObjectName("dangerButton")
        self.stop.setEnabled(False)
        self.stop.setAccessibleName("Stop response")

        self.core = _VoiceOrbWidget()
        self.activity = ActivityRail()
        self.activity.setObjectName("liveActivityCard")
        self.activity_toggle = QPushButton("Hide activity")
        self.activity_toggle.clicked.connect(self._toggle_activity)
        self.activity_toggle.setVisible(False)

        self.voice_state = QLabel("READY")
        self.voice_state.setObjectName("orbState")
        self.voice_state.setAccessibleName("Voice interaction state")

        # Left context rail
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_InfoCard(
            "System State",
            "●  Active",
            "Virgo is ready and listening.",
            accent="#52e09b",
            object_name="systemStateCard",
        ))
        self.focus_card = _InfoCard(
            "Current Focus",
            "Listening for your command",
            "Say something or press Push-to-talk.",
            accent="#c06cff",
            object_name="focusCard",
        )
        left.addWidget(self.focus_card)
        self.context_card = _ContextCard()
        left.addWidget(self.context_card)
        left.addWidget(_ShortcutCard())
        left.addWidget(_InfoCard(
            "Made for you.",
            "Learns with you.",
            "Works with your local session, memory and approved capabilities.",
            accent="#c06cff",
            object_name="madeForYouCard",
        ))
        left.addStretch(1)

        left_panel = QWidget()
        left_panel.setObjectName("dashboardRail")
        left_panel.setLayout(left)

        # Center voice workspace
        center = QVBoxLayout()
        center.setContentsMargins(6, 0, 6, 0)
        center.setSpacing(10)

        greeting = QLabel("Good to see you. 👋")
        greeting.setObjectName("greetingTitle")
        subtitle = QLabel(
            "I'm Virgo, your AI companion and personal assistant.\n"
            "I'm here to listen, understand and help — naturally."
        )
        subtitle.setObjectName("greetingSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(greeting, alignment=Qt.AlignmentFlag.AlignHCenter)
        center.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        center.addWidget(self.core, 1)
        center.addWidget(self.voice_state, alignment=Qt.AlignmentFlag.AlignHCenter)

        modes = QHBoxLayout()
        modes.setSpacing(8)
        modes.addStretch(1)
        self.voice_mode_status = QLabel("♬  Voice Mode  •  ON")
        self.voice_mode_status.setObjectName("modePillLabel")
        self.push_to_talk_status = QLabel("⌕  Push-to-talk  •  READY")
        self.push_to_talk_status.setObjectName("modePillLabel")
        self.interrupt = QLabel("⚡  Interrupt  •  ON")
        self.interrupt.setObjectName("modePillLabel")
        modes.addWidget(self.voice_mode_status)
        modes.addWidget(self.push_to_talk_status)
        modes.addWidget(self.interrupt)
        modes.addStretch(1)
        center.addLayout(modes)

        self.current_action_title = QLabel("Current Action")
        self.current_action_title.setObjectName("cardTitle")
        self.current_action = QLabel("Waiting for your command…")
        self.current_action.setObjectName("currentAction")
        action_card = QFrame()
        action_card.setObjectName("currentActionCard")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(14, 10, 14, 10)
        action_layout.addWidget(self.current_action_title)
        action_layout.addWidget(self.current_action)
        center.addWidget(action_card)
        center.addWidget(self.transcript)

        # Real controls, arranged to match the target visual language.
        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.setContentsMargins(0, 4, 0, 0)
        controls.addWidget(self.stop)
        controls.addWidget(self.push_to_talk)
        controls.addWidget(self.voice_mode)
        controls.addStretch(1)
        controls.addWidget(self.text_input, 1)
        controls.addWidget(self.send)
        center.addLayout(controls)

        center_panel = QWidget()
        center_panel.setObjectName("voiceWorkspace")
        center_panel.setLayout(center)

        # Right insight rail
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.activity)
        right.addWidget(_TrustSafetyCard())
        self.capabilities_card = _CapabilitiesCard()
        right.addWidget(self.capabilities_card)
        right.addWidget(_InfoCard(
            "Virgo Memory",
            "Enabled",
            "You & Virgo  •  Connected",
            accent="#52e09b",
            object_name="memoryCard",
        ))
        right.addStretch(1)
        right_panel = QWidget()
        right_panel.setObjectName("dashboardRail")
        right_panel.setLayout(right)

        dashboard = QHBoxLayout(self)
        dashboard.setContentsMargins(0, 0, 0, 0)
        dashboard.setSpacing(12)
        dashboard.addWidget(left_panel, 0)
        dashboard.addWidget(center_panel, 1)
        dashboard.addWidget(right_panel, 0)
        dashboard.setStretchFactor(center_panel, 1)

    def _toggle_activity(self) -> None:
        visible = self.activity.isHidden()
        self.activity.setVisible(visible)
        self.activity_toggle.setText("Hide activity" if visible else "Show activity")

    def set_model_readiness(self, models: Iterable[str]) -> None:
        values = tuple(models)
        ready = bool(values)
        if ready:
            primary = next((name for name in values if name.startswith("virgo-slm")), values[0])
            fallback = next((name for name in values if not name.startswith("virgo-slm")), None)
            self.voice_mode_status.setText("♬  Voice Mode  •  READY")
            self.current_action.setText(
                f"Virgo SLM ready  •  {primary}"
                + (f"  •  Ollama fallback available: {fallback}" if fallback else "")
            )
        else:
            self.voice_mode_status.setText("♬  Voice Mode  •  WAITING")
            self.current_action.setText("Install or select a local model to start chatting.")

    def set_voice_state(self, state_name: str) -> None:
        label = {
            "idle": "Ready",
            "listening": "Listening",
            "processing_speech": "Understanding",
            "thinking": "Thinking",
            "planning": "Planning",
            "researching": "Researching",
            "working": "Working",
            "verifying": "Verifying",
            "waiting_for_permission": "Waiting for permission",
            "responding": "Responding",
            "speaking": "Speaking",
            "interrupted": "Interrupted",
            "recovering": "Recovering",
            "offline": "Offline",
            "error": "Needs attention",
        }.get(state_name, state_name.replace("_", " ").title())
        self.voice_state.setText(label)
        self.core.set_state(state_name)

    def present_state(self, state_name: str, message: str) -> None:
        self.set_voice_state(state_name)
        self.current_action.setText(message)
        self.focus_card.set_values(label=message)
        self.activity.present_state(state_name, message)

    def append_message(self, role: str, text: str) -> None:
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        prefix = "\n\n" if self.transcript.toPlainText() else ""
        cursor.insertText(f"{prefix}{role}:\n{text}")
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def append_assistant_chunk(self, text: str) -> None:
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def set_busy(self, busy: bool) -> None:
        self.text_input.setEnabled(not busy)
        self.send.setEnabled(not busy)
        self.push_to_talk.setEnabled(not busy)
        self.voice_mode.setEnabled(not busy)
        self.stop.setEnabled(busy)
        self.current_action.setText("Working on your request…" if busy else "Waiting for your command…")


class _VoiceOrbWidget(QFrame):
    """Paint a neon voice orb with a lightweight animated waveform."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("voiceOrb")
        self.setMinimumSize(280, 280)
        self._state = "idle"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.10) % (2 * 3.1415926535)
        self.update()

    def set_state(self, state_name: str) -> None:
        self._state = state_name
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        center = rect.center()
        size = min(rect.width(), rect.height())
        outer = size * 0.31
        inner = size * 0.25

        # Ambient rings
        for extra, alpha in ((0.17, 28), (0.11, 44), (0.06, 72)):
            pen = QPen(QColor(165, 73, 255, alpha), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            radius = outer * (1 + extra)
            p.drawEllipse(center, int(radius), int(radius))

        glow = QRadialGradient(center, inner * 1.05)
        glow.setColorAt(0.0, QColor(255, 92, 232, 130))
        glow.setColorAt(0.42, QColor(117, 82, 255, 72))
        glow.setColorAt(1.0, QColor(17, 10, 42, 0))
        p.setBrush(glow)
        p.setPen(QPen(QColor(193, 99, 255, 210), 2))
        p.drawEllipse(center, int(outer), int(outer))

        core = QRadialGradient(center, inner)
        core.setColorAt(0.0, QColor(30, 12, 57, 240))
        core.setColorAt(0.7, QColor(12, 14, 34, 245))
        core.setColorAt(1.0, QColor(5, 8, 22, 245))
        p.setBrush(core)
        p.setPen(QPen(QColor(137, 80, 255, 220), 2))
        p.drawEllipse(center, int(inner), int(inner))

        # Waveform
        wave = QLinearGradient(rect.left(), 0, rect.right(), 0)
        wave.setColorAt(0.0, QColor(255, 91, 226, 170))
        wave.setColorAt(0.5, QColor(149, 79, 255, 255))
        wave.setColorAt(1.0, QColor(54, 133, 255, 220))
        pen = QPen(QBrush(wave), max(2, int(size * 0.009)))
        p.setPen(pen)
        path = QPainterPath()
        import math
        y0 = center.y()
        start_x = int(center.x() - inner * 0.82)
        end_x = int(center.x() + inner * 0.82)
        width = max(1, end_x - start_x)
        for i in range(81):
            x = start_x + width * i / 80
            t = i / 80 * math.pi * 2.8
            amplitude = inner * (0.045 + 0.032 * (1 + math.sin(self._phase)) / 2)
            y = y0 + math.sin(t + self._phase) * amplitude
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.drawPath(path)
        p.setBrush(QColor(255, 176, 255, 235))
        p.setPen(QPen(QColor(255, 232, 255, 230), 1))
        p.drawEllipse(center, max(4, int(size * 0.011)), max(4, int(size * 0.011)))
        p.end()


class _InfoCard(QFrame):
    def __init__(self, title: str, value: str, detail: str, *, accent: str, object_name: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 11)
        title_label = QLabel(title)
        title_label.setObjectName("cardEyebrow")
        self.value = QLabel(value)
        self.value.setObjectName("cardValue")
        self.value.setStyleSheet(f"color: {accent};")
        detail_label = QLabel(detail)
        detail_label.setObjectName("cardDetail")
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(self.value)
        layout.addWidget(detail_label)

    def set_values(self, *, label: str | None = None, value: str | None = None) -> None:
        if label is not None:
            self.value.setText(label)
        if value is not None:
            self.value.setText(value)


class _ContextCard(_InfoCard):
    def __init__(self) -> None:
        super().__init__(
            "Context",
            "Session  •  Active",
            "You & Virgo  •  Connected\nMemory  •  Enabled\nVoice Mode  •  Ready",
            accent="#52e09b",
            object_name="contextCard",
        )


class _ShortcutCard(_InfoCard):
    def __init__(self) -> None:
        super().__init__(
            "Shortcuts",
            "Open VS Code  ›",
            "Research Anything  ›\nCreate Image  ›\nScreen Learning  ›",
            accent="#d9c7ff",
            object_name="shortcutsCard",
        )


class _TrustSafetyCard(_InfoCard):
    def __init__(self) -> None:
        super().__init__(
            "Trust & Safety",
            "✓  Verified",
            "Every action is documented.\nSanitized  •  Verified  •  Private",
            accent="#52e09b",
            object_name="trustSafetyCard",
        )


class _CapabilitiesCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("capabilitiesCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 11)
        title = QLabel("Capabilities")
        title.setObjectName("cardEyebrow")
        layout.addWidget(title)
        grid = QGridLayout()
        items = (
            ("Conversation", "Active", "#52e09b"),
            ("Voice & STT", "Active", "#52e09b"),
            ("TTS Speech", "Active", "#52e09b"),
            ("Image Gen", "Ready", "#9ea8bd"),
            ("Desktop Ctrl", "Not Configured", "#ffb05c"),
            ("Internet Res", "Not Configured", "#ffb05c"),
        )
        for index, (name, status, color) in enumerate(items):
            card = QFrame()
            card.setObjectName("capabilityTile")
            tile = QVBoxLayout(card)
            tile.setContentsMargins(8, 7, 8, 7)
            n = QLabel(name)
            n.setObjectName("tileName")
            s = QLabel(status)
            s.setStyleSheet(f"color: {color}; font-weight: 650;")
            tile.addWidget(n)
            tile.addWidget(s)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        view_all = QLabel("View all capabilities  ›")
        view_all.setObjectName("viewAll")
        layout.addWidget(view_all)


class SessionsView(_LabeledView):
    def __init__(self) -> None:
        super().__init__("Session history", "Reopen locally persisted conversations.")
        self.sessions = QListWidget()
        self.sessions.setAccessibleName("Session history")
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.new_session = QPushButton("New session")
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search session titles and messages")
        self.query.setAccessibleName("Search sessions")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Session title")
        self.rename = QPushButton("Rename")
        self.archive = QPushButton("Archive")
        self.restore = QPushButton("Restore")
        self.delete = QPushButton("Delete")
        self.show_archived = QCheckBox("Show archived")
        self.storage = QLabel("Storage usage unavailable")
        row = QHBoxLayout()
        row.addWidget(self.sessions, stretch=1)
        row.addWidget(self.history, stretch=2)
        self.content_layout.addLayout(row, stretch=1)
        controls = QGridLayout()
        controls.addWidget(self.query, 0, 0, 1, 3)
        controls.addWidget(self.show_archived, 0, 3)
        controls.addWidget(self.title, 1, 0, 1, 2)
        controls.addWidget(self.rename, 1, 2)
        controls.addWidget(self.new_session, 1, 3)
        controls.addWidget(self.archive, 2, 0)
        controls.addWidget(self.restore, 2, 1)
        controls.addWidget(self.delete, 2, 2)
        controls.addWidget(self.storage, 2, 3)
        self.content_layout.addLayout(controls)

    def set_sessions(self, titles: Iterable[str]) -> None:
        self.sessions.clear()
        self.sessions.addItems(list(titles))


class HealthView(_LabeledView):
    COMPONENTS = (
        "STT",
        "Local LLM",
        "TTS",
        "Microphone",
        "Speaker",
        "Storage",
        "Rust core",
    )

    def __init__(self) -> None:
        super().__init__(
            "Provider and device health",
            "Safe readiness summaries for local Stage 1 components.",
        )
        self.results = QListWidget()
        self.results.setAccessibleName("Provider health results")
        self.set_results((component, "Unknown") for component in self.COMPONENTS)
        self.refresh = QPushButton("Refresh")
        self.content_layout.addWidget(self.results, stretch=1)
        self.content_layout.addWidget(self.refresh)

    def set_results(self, results: Iterable[tuple[str, str]]) -> None:
        self.results.clear()
        self.results.addItems([f"{name}: {status}" for name, status in results])


class SettingsView(_LabeledView):
    def __init__(self) -> None:
        super().__init__(
            "Settings and local selection",
            "Select existing local models, voices, microphones, and speakers.",
        )
        form = QFormLayout()
        self.model = QComboBox()
        self.microphone = QComboBox()
        self.speaker = QComboBox()
        self.voice = QComboBox()
        self.voice_status = QLabel("Voice profile not loaded")
        self.custom_voice_status = QLabel("Custom voice cloning: NOT_CONFIGURED")
        form.addRow("Local model", self.model)
        form.addRow("Microphone", self.microphone)
        form.addRow("Speaker", self.speaker)
        form.addRow("Voice", self.voice)
        form.addRow("Voice identity", self.voice_status)
        form.addRow("Custom voice", self.custom_voice_status)
        self.content_layout.addLayout(form)
        self.content_layout.addStretch()

    def set_options(
        self,
        *,
        models: Iterable[str] = (),
        microphones: Iterable[str] = (),
        speakers: Iterable[str] = (),
        voices: Iterable[str] = (),
    ) -> None:
        for combo, values in (
            (self.model, models),
            (self.microphone, microphones),
            (self.speaker, speakers),
            (self.voice, voices),
        ):
            combo.clear()
            combo.addItems(list(values))


class PermissionsView(_LabeledView):
    def __init__(self) -> None:
        super().__init__(
            "Permissions",
            "Virgo requests approval before actions that affect the system or data.",
        )
        self.summary = QListWidget()
        self.summary.addItems(
            (
                "Microphone: user controlled",
                "Speaker: user controlled",
                "Cloud providers: disabled without consent",
                "Dangerous actions: explicit permission required",
            )
        )
        self.content_layout.addWidget(self.summary, stretch=1)


class DiagnosticsView(_LabeledView):
    def __init__(self) -> None:
        super().__init__(
            "Logs and diagnostics",
            "Safe local diagnostics omit secrets, conversations, and raw audio.",
        )
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("No diagnostic snapshot collected")
        self.refresh = QPushButton("Refresh diagnostics")
        self.content_layout.addWidget(self.output, stretch=1)
        self.content_layout.addWidget(self.refresh)

    def set_summary(self, summary: str) -> None:
        self.output.setPlainText(summary)


class CreationView(_LabeledView):
    """Functional controlled-creation workspace without presentation logic."""

    def __init__(self) -> None:
        super().__init__(
            "Creation workspace",
            "Plan and preview local changes before explicit approval and apply.",
        )
        self.content_layout.addWidget(
            WorkflowStepper(
                (
                    "Request",
                    "Analyze",
                    "Plan",
                    "Preview",
                    "Approve",
                    "Apply",
                    "Validate",
                    "Accept / Rollback",
                )
            )
        )
        form = QFormLayout()
        self.workspace = QLineEdit()
        self.workspace.setPlaceholderText("Absolute local workspace path")
        self.request = QTextEdit()
        self.request.setPlaceholderText("Describe the local file creation or edit")
        self.request.setMaximumHeight(80)
        form.addRow("Workspace", self.workspace)
        form.addRow("Request", self.request)
        self.analyze = QPushButton("Analyze and plan")
        self.capability = QLabel("Capability: Not detected")
        self.provider = QLabel("Provider/model: Not selected")
        self.specification = QTextEdit()
        self.specification.setReadOnly(True)
        self.specification.setMaximumHeight(100)
        self.plan = QListWidget()
        self.plan.setAccessibleName("Creation plan")
        self.files = QListWidget()
        self.files.setAccessibleName("Proposed files")
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("No preview prepared")
        self.approval_summary = QLabel("No mutation approved")
        self.approval_summary.setWordWrap(True)
        self.approve = QPushButton("Approve exact preview")
        self.apply = QPushButton("Apply approved changes")
        self.accept = QPushButton("Accept changes")
        self.rollback = QPushButton("Rollback changes")
        self.task_status = QLabel("Task status: IDLE")
        self.validation_status = QLabel("Validation/Test: Not run")
        for button in (self.approve, self.apply, self.accept, self.rollback):
            button.setEnabled(False)
        controls = QHBoxLayout()
        for button in (self.approve, self.apply, self.accept, self.rollback):
            controls.addWidget(button)
        self.content_layout.addLayout(form)
        self.content_layout.addWidget(self.analyze)
        self.content_layout.addWidget(self.capability)
        self.content_layout.addWidget(self.provider)
        self.content_layout.addWidget(QLabel("Enriched specification / findings"))
        self.content_layout.addWidget(self.specification)
        self.content_layout.addWidget(QLabel("Plan"))
        self.content_layout.addWidget(self.plan)
        self.content_layout.addWidget(QLabel("Proposed files"))
        self.content_layout.addWidget(self.files)
        self.content_layout.addWidget(QLabel("Preview / diff"))
        self.content_layout.addWidget(self.preview, stretch=1)
        self.content_layout.addWidget(self.approval_summary)
        self.content_layout.addLayout(controls)
        self.content_layout.addWidget(self.validation_status)
        self.content_layout.addWidget(self.task_status)

    def set_busy(self, busy: bool) -> None:
        self.analyze.setEnabled(not busy)
        if busy:
            for button in (self.approve, self.apply, self.accept, self.rollback):
                button.setEnabled(False)

    def set_status(self, status: str) -> None:
        self.task_status.setText(f"Task status: {status.upper()}")


class SecurityView(_LabeledView):
    """Read-only, explicitly scoped Stage 3 security workspace."""

    def __init__(self) -> None:
        super().__init__(
            "Security workspace",
            "SAFE MODE: defensive analysis is read-only by default; active localhost visibility and remediation require explicit approval.",
        )
        self.content_layout.addWidget(
            WorkflowStepper(
                (
                    "Authorize",
                    "Configure",
                    "Analyze",
                    "Findings",
                    "Recommendation",
                    "Remediate",
                    "Verify / Rollback",
                )
            )
        )
        form = QFormLayout()
        self.workspace = QLineEdit()
        self.workspace.setPlaceholderText("Absolute authorized workspace path")
        self.ownership = QCheckBox(
            "I own or am explicitly authorized to assess this target"
        )
        self.objective = QComboBox()
        self.objective.addItems(
            (
                "Secure code review",
                "Configuration audit",
                "Dependency assessment",
                "Log analysis",
                "Lab security assessment",
            )
        )
        self.scope = QLabel("Scope: local project / read-only / network disabled")
        self.scope.setWordWrap(True)
        self.analysis_type = QComboBox()
        self.analysis_type.addItems(("Project assessment", "Project + selected logs"))
        self.selected_logs = QLineEdit()
        self.selected_logs.setPlaceholderText(
            "Optional comma-separated relative .log paths"
        )
        self.selected_checks = QLabel(
            "Checks: code, secrets, configuration, dependencies, selected logs"
        )
        self.selected_checks.setWordWrap(True)
        form.addRow("Authorized workspace", self.workspace)
        form.addRow("Authorization", self.ownership)
        form.addRow("Defensive objective", self.objective)
        form.addRow("Assessment", self.analysis_type)
        form.addRow("Selected logs", self.selected_logs)
        form.addRow("Scope", self.scope)
        form.addRow("Selected checks", self.selected_checks)
        controls = QHBoxLayout()
        self.analyze = QPushButton("Analyze read-only")
        self.cancel = QPushButton("Cancel")
        self.cancel.setEnabled(False)
        controls.addWidget(self.analyze)
        controls.addWidget(self.cancel)
        self.status = QLabel("Analysis status: IDLE")
        self.summary = QLabel("No report")
        self.summary.setWordWrap(True)
        self.provider = QLabel("Vulnerability intelligence: NOT_CONFIGURED")
        self.assessment_plan = QLabel(
            "Plan: scope → inventory → checks → findings → recommendations → verification"
        )
        self.assessment_plan.setWordWrap(True)
        system_controls = QHBoxLayout()
        self.diagnostics = QPushButton("Read-only system diagnostics")
        self.network_authorization = QCheckBox(
            "Authorize one localhost TCP reachability check"
        )
        self.network_port = QLineEdit()
        self.network_port.setPlaceholderText("localhost port")
        self.network_check = QPushButton("Check authorized localhost endpoint")
        system_controls.addWidget(self.diagnostics)
        system_controls.addWidget(self.network_authorization)
        system_controls.addWidget(self.network_port)
        system_controls.addWidget(self.network_check)
        self.network_status = QLabel("NETWORK DISABLED")
        filters = QHBoxLayout()
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(
            ("All severities", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
        )
        self.category_filter = QComboBox()
        self.category_filter.addItems(
            (
                "All categories",
                "SECRET_EXPOSURE",
                "INSECURE_CONFIGURATION",
                "DANGEROUS_CODE",
                "DEPENDENCY_CONFIGURATION",
                "LOG_SECURITY",
                "MALWARE_INDICATOR",
            )
        )
        filters.addWidget(self.severity_filter)
        filters.addWidget(self.category_filter)
        self.findings = QListWidget()
        self.findings.setAccessibleName("Security findings")
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Select a finding to view redacted evidence and recommendation"
        )
        remediation_controls = QHBoxLayout()
        self.remediation_preview = QPushButton("Preview selected remediation")
        self.remediation_apply = QPushButton("Approve, apply, and verify")
        self.remediation_rollback = QPushButton("Rollback remediation")
        self.remediation_apply.setEnabled(False)
        self.remediation_rollback.setEnabled(False)
        remediation_controls.addWidget(self.remediation_preview)
        remediation_controls.addWidget(self.remediation_apply)
        remediation_controls.addWidget(self.remediation_rollback)
        self.remediation_status = QLabel("Remediation: no mutation approved")
        self.content_layout.addLayout(form)
        self.content_layout.addLayout(controls)
        self.content_layout.addWidget(self.status)
        self.content_layout.addWidget(self.summary)
        self.content_layout.addWidget(self.provider)
        self.content_layout.addWidget(self.assessment_plan)
        self.content_layout.addLayout(system_controls)
        self.content_layout.addWidget(self.network_status)
        self.content_layout.addLayout(filters)
        self.content_layout.addWidget(QLabel("Findings / observations / errors"))
        self.content_layout.addWidget(self.findings, stretch=1)
        self.content_layout.addWidget(self.details, stretch=1)
        self.content_layout.addLayout(remediation_controls)
        self.content_layout.addWidget(self.remediation_status)

    def set_busy(self, busy: bool) -> None:
        self.analyze.setEnabled(not busy)
        self.workspace.setEnabled(not busy)
        self.analysis_type.setEnabled(not busy)
        self.selected_logs.setEnabled(not busy)
        self.ownership.setEnabled(not busy)
        self.objective.setEnabled(not busy)
        self.diagnostics.setEnabled(not busy)
        self.network_check.setEnabled(not busy)
        self.cancel.setEnabled(busy)
        if busy:
            self.status.setText("Analysis status: ANALYZING")


class LearningView(_LabeledView):
    """Visible review surface for controlled local learning."""

    def __init__(self) -> None:
        super().__init__(
            "Learning and verified knowledge",
            "No hidden learning: research is permissioned, evidence is reviewed, and only accepted knowledge persists.",
        )
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(10)
        self.content_layout.addWidget(
            WorkflowStepper(
                (
                    "Knowledge",
                    "Verified knowledge",
                    "Experience & skills",
                    "Self-inspection",
                    "Improvement",
                )
            )
        )
        form = QFormLayout()
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("Knowledge topic")
        self.question = QLineEdit()
        self.question.setPlaceholderText(
            "Question Virgo cannot answer from verified knowledge"
        )
        self.scope_key = QLineEdit("default")
        self.document = QLineEdit()
        self.document.setPlaceholderText(
            "Absolute path to an explicitly approved text document"
        )
        form.addRow("Topic", self.topic)
        form.addRow("Question", self.question)
        form.addRow("Project scope", self.scope_key)
        form.addRow("Approved local source", self.document)
        self.network = QLabel("INTERNET RESEARCH: DISABLED / PROVIDER NOT_CONFIGURED")
        self.gap = QLabel("Knowledge gap: not evaluated")
        self.permission = QLabel("Research permission: not requested")
        for label in (self.network, self.gap, self.permission):
            label.setWordWrap(True)
            label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
        permission_controls = QGridLayout()
        self.detect = QPushButton("Detect knowledge gap")
        self.request = QPushButton("Request local research permission")
        self.deny = QPushButton("Deny")
        self.approve = QPushButton("Allow once and inspect source")
        permission_controls.addWidget(self.detect, 0, 0)
        permission_controls.addWidget(self.request, 0, 1)
        permission_controls.addWidget(self.deny, 1, 0)
        permission_controls.addWidget(self.approve, 1, 1)
        self.claims = QListWidget()
        self.claims.setMinimumHeight(100)
        self.claims.setAccessibleName("Candidate knowledge claims")
        self.details = QTextEdit()
        self.details.setMinimumHeight(110)
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Source, quality reasons, confidence, and contradictions"
        )
        review_controls = QGridLayout()
        self.accept = QPushButton("Accept verified proposal")
        self.reject = QPushButton("Reject proposal")
        self.retrieve = QPushButton("Retrieve verified knowledge")
        self.forget = QPushButton("Forget selected knowledge")
        review_controls.addWidget(self.accept, 0, 0)
        review_controls.addWidget(self.reject, 0, 1)
        review_controls.addWidget(self.retrieve, 1, 0)
        review_controls.addWidget(self.forget, 1, 1)
        self.accept.setEnabled(False)
        self.status = QLabel("Learning status: IDLE")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self.content_layout.addLayout(form)
        self.content_layout.addWidget(self.network)
        self.content_layout.addWidget(self.gap)
        self.content_layout.addWidget(self.permission)
        self.content_layout.addLayout(permission_controls)
        self.content_layout.addWidget(QLabel("Candidate / stored claims"))
        self.content_layout.addWidget(self.claims, stretch=1)
        self.content_layout.addWidget(self.details, stretch=1)
        self.content_layout.addLayout(review_controls)
        self.content_layout.addWidget(self.status)
        self.content_layout.addWidget(
            QLabel("Self-inspection and improvement proposals")
        )
        inspection_form = QFormLayout()
        self.inspection_root = QLineEdit()
        self.inspection_root.setPlaceholderText("Absolute authorized repository path")
        self.inspection_authorization = QCheckBox(
            "I authorize bounded read-only inspection of this exact repository"
        )
        self.inspection_categories = QLabel(
            "Static, dependencies, architecture, performance, security, tests, failures"
        )
        self.inspection_categories.setWordWrap(True)
        inspection_form.addRow("Repository", self.inspection_root)
        inspection_form.addRow("Authorization", self.inspection_authorization)
        inspection_form.addRow("Categories", self.inspection_categories)
        inspection_controls = QHBoxLayout()
        self.inspect = QPushButton("Run bounded self-inspection")
        self.cancel_inspection = QPushButton("Cancel inspection")
        self.cancel_inspection.setEnabled(False)
        inspection_controls.addWidget(self.inspect)
        inspection_controls.addWidget(self.cancel_inspection)
        self.inspection_findings = QListWidget()
        self.inspection_findings.setMinimumHeight(100)
        self.inspection_findings.setAccessibleName("Self-inspection findings")
        self.improvement = QTextEdit()
        self.improvement.setMinimumHeight(120)
        self.improvement.setReadOnly(True)
        self.improvement.setPlaceholderText(
            "Lessons, skill metadata, evaluations, and proposal-only improvements"
        )
        skill_controls = QHBoxLayout()
        self.accept_skill = QPushButton("Accept validated structured skill")
        self.reject_skill = QPushButton("Reject skill candidate")
        self.accept_skill.setEnabled(False)
        skill_controls.addWidget(self.accept_skill)
        skill_controls.addWidget(self.reject_skill)
        self.self_update_boundary = QLabel(
            "PRODUCTION SELF-MODIFICATION: DISABLED — Step 2 stops at risk-estimated proposals"
        )
        self.self_update_boundary.setWordWrap(True)
        self.self_update_boundary.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self.content_layout.addLayout(inspection_form)
        self.content_layout.addLayout(inspection_controls)
        self.content_layout.addWidget(self.inspection_findings, stretch=1)
        self.content_layout.addWidget(self.improvement, stretch=1)
        self.content_layout.addLayout(skill_controls)
        self.content_layout.addWidget(self.self_update_boundary)
        self.content_layout.addWidget(QLabel("Controlled self-improvement review"))
        self.self_improvement_root = QLineEdit()
        self.self_improvement_target = QLineEdit()
        self.self_improvement_baseline = QLineEdit()
        self.self_improvement_content = QTextEdit()
        self.self_improvement_content.setMinimumHeight(120)
        self.self_improvement_content.setPlaceholderText(
            "Exact proposed UTF-8 content for the isolated approved target"
        )
        improvement_form = QFormLayout()
        improvement_form.addRow("Repository", self.self_improvement_root)
        improvement_form.addRow("Exact target", self.self_improvement_target)
        improvement_form.addRow("Baseline HEAD", self.self_improvement_baseline)
        improvement_form.addRow("Proposed content", self.self_improvement_content)
        self.prepare_improvement = QPushButton("Prepare diff — NO CHANGES MADE YET")
        self.deny_improvement = QPushButton("Deny")
        self.apply_improvement = QPushButton("Approve and apply isolated candidate")
        self.accept_improvement = QPushButton("Accept verified candidate")
        self.rollback_improvement = QPushButton("Rollback candidate")
        self.cancel_improvement = QPushButton("Cancel at safe point")
        self.apply_improvement.setEnabled(False)
        self.accept_improvement.setEnabled(False)
        self.rollback_improvement.setEnabled(False)
        improvement_controls = QGridLayout()
        for index, button in enumerate(
            (
                self.prepare_improvement,
                self.deny_improvement,
                self.apply_improvement,
                self.accept_improvement,
                self.rollback_improvement,
                self.cancel_improvement,
            )
        ):
            improvement_controls.addWidget(button, index // 3, index % 3)
        self.self_improvement_status = QLabel("APPROVAL REQUIRED — NO CHANGES MADE YET")
        self.self_improvement_status.setWordWrap(True)
        self.self_improvement_status.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self.self_improvement_report = QTextEdit()
        self.self_improvement_report.setMinimumHeight(150)
        self.self_improvement_report.setReadOnly(True)
        self.self_improvement_report.setPlaceholderText(
            "Problem, evidence, risk, exact files, diff, branch, tests, security, evaluation, and rollback"
        )
        self.content_layout.addLayout(improvement_form)
        self.content_layout.addLayout(improvement_controls)
        self.content_layout.addWidget(self.self_improvement_status)
        self.content_layout.addWidget(self.self_improvement_report, stretch=1)
        for field in self.findChildren(QLineEdit):
            field.setMinimumHeight(28)
        for button in self.findChildren(QPushButton):
            button.setMinimumHeight(30)


class PersonalRuntimeView(_LabeledView):
    """Inspectable conversation-centric task, agent, and preference surface."""

    def __init__(self) -> None:
        super().__init__(
            "Personal AI Runtime",
            "Bounded agents, permissions, provider status, verification, and preferences.",
        )
        self.objective = QLineEdit()
        self.objective.setPlaceholderText(
            "Ask Virgo to research, create, code, or plan"
        )
        self.plan = QTextEdit()
        self.plan.setReadOnly(True)
        self.status = QLabel("Task status: IDLE")
        self.prepare = QPushButton("Prepare task")
        self.approve = QPushButton("Approve exact task")
        self.run = QPushButton("Run")
        self.cancel = QPushButton("Cancel")
        controls = QHBoxLayout()
        for button in (self.prepare, self.approve, self.run, self.cancel):
            controls.addWidget(button)
        self.preference_key = QLineEdit("response_style")
        self.preference_value = QLineEdit()
        self.preference_value.setPlaceholderText("Explicit non-sensitive preference")
        self.remember = QPushButton("Remember / correct")
        self.forget = QPushButton("Forget")
        preference_controls = QHBoxLayout()
        preference_controls.addWidget(self.preference_key)
        preference_controls.addWidget(self.preference_value)
        preference_controls.addWidget(self.remember)
        preference_controls.addWidget(self.forget)
        self.preferences = QTextEdit()
        self.preferences.setReadOnly(True)
        self.providers = QLabel(
            "Local conversation: AVAILABLE | Vision/screen: NOT_CONFIGURED_DEFERRED | "
            "Browser/research/image/video: NOT_CONFIGURED"
        )
        self.providers.setWordWrap(True)
        self.content_layout.addWidget(self.objective)
        self.content_layout.addLayout(controls)
        self.content_layout.addWidget(self.status)
        self.content_layout.addWidget(self.plan, stretch=1)
        self.content_layout.addWidget(QLabel("Inspectable preferences"))
        self.content_layout.addLayout(preference_controls)
        self.content_layout.addWidget(self.preferences)
        self.content_layout.addWidget(self.providers)


class StageOneScreens(QWidget):
    """Phase 2 navigation host retaining the Phase 1 controller-facing API."""

    SCREEN_NAMES = (
        "Home",
        "Onboarding",
        "Conversation",
        "Sessions",
        "Health",
        "Settings",
        "Permissions",
        "Diagnostics",
        "Creation",
        "Security",
        "Learning",
        "Personal AI",
    )

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.onboarding = OnboardingView()
        self.conversation = ConversationView()
        self.sessions = SessionsView()
        self.health = HealthView()
        self.settings = SettingsView()
        self.permissions = PermissionsView()
        self.diagnostics = DiagnosticsView()
        self.creation = CreationView()
        self.security = SecurityView()
        self.learning = LearningView()
        self.learning_scroll = QScrollArea()
        self.learning_scroll.setWidgetResizable(True)
        self.learning_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.learning_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.learning_scroll.setWidget(self.learning)
        self.personal_ai = PersonalRuntimeView()
        self.stack = QStackedWidget()
        self._page_names = self.SCREEN_NAMES[1:]
        for name, view in zip(
            self._page_names,
            (
                self.onboarding,
                self.conversation,
                self.sessions,
                self.health,
                self.settings,
                self.permissions,
                self.diagnostics,
                self.creation,
                self.security,
                self.learning_scroll,
                self.personal_ai,
            ),
            strict=True,
        ):
            scroll = view
            if name in {"Creation", "Security", "Personal AI"}:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QScrollArea.Shape.NoFrame)
                scroll.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )
                scroll.setWidget(view)
            self.stack.addWidget(scroll)
        self.navigation = NavigationRail(self.SCREEN_NAMES, self.select_screen)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.select_screen("Home")

    def select_screen(self, name: str) -> None:
        if name not in self.SCREEN_NAMES:
            raise ValueError(f"Unknown Stage 1 screen: {name}")
        actual = "Conversation" if name == "Home" else name
        self.stack.setCurrentIndex(self._page_names.index(actual))
        self._selected_name = name
        self.navigation.select(name)

    def currentIndex(self) -> int:  # noqa: N802
        return self.SCREEN_NAMES.index(self._selected_name)

    def currentWidget(self) -> QWidget:  # noqa: N802
        """Retain the former tab host's presentation-only query API."""
        current = self.stack.currentWidget()
        assert current is not None
        return current

    def tabText(self, index: int) -> str:  # noqa: N802
        return self.SCREEN_NAMES[index]
