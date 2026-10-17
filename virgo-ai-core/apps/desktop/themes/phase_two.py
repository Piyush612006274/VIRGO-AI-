"""Central Phase 2 presentation tokens and native Qt stylesheet."""

BACKGROUND, SURFACE, RAISED = "#050811", "#0b1220", "#101a2b"
CYAN, BLUE, VIOLET = "#55e9ff", "#2f7dff", "#8b5cf6"
GREEN, AMBER, RED = "#48d597", "#f5b942", "#ff5c75"
TEXT, MUTED, LINE = "#e8f3ff", "#8ca0b8", "#20324d"
SPACING, RADIUS, MOTION_MS = 12, 12, 700

PHASE_TWO_STYLE = f"""
QWidget {{ color: {TEXT}; background-color: {BACKGROUND}; font-size: 13px; }}
QMainWindow, QWidget#appShell {{ background: {BACKGROUND}; }}
QFrame#panel, QFrame#navigationRail, QFrame#virgoCore, QFrame#activityRail {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS}px; }}
QLabel#applicationTitle {{ color: {CYAN}; font-size: 20px; font-weight: 700; }}
QLabel#headerTagline {{ color: #737d96; font-size: 10px; font-weight: 600; }}
QLabel#screenTitle {{ color: {TEXT}; font-size: 22px; font-weight: 650; }}
QLabel#sectionTitle {{ color: {CYAN}; font-size: 15px; font-weight: 650; }}
QLabel#muted {{ color: {MUTED}; }}
QPushButton {{ background: {RAISED}; border: 1px solid {LINE}; border-radius: 8px; padding: 8px 12px; min-height: 18px; }}
QPushButton:hover {{ border-color: {CYAN}; }}
QPushButton:focus {{ border: 2px solid {CYAN}; }}
QPushButton:checked, QPushButton#primary {{ background: #123250; border-color: {CYAN}; }}
QPushButton#danger {{ border-color: {RED}; color: #ffdbe1; }}
QPushButton:disabled {{ color: #607189; background: #0a101b; border-color: #172338; }}
QLineEdit, QTextEdit, QListWidget, QComboBox {{ background: #070d18; border: 1px solid {LINE}; border-radius: 8px; padding: 7px; selection-background-color: {BLUE}; }}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus, QComboBox:focus {{ border-color: {CYAN}; }}
QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport {{ border: none; background: {BACKGROUND}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #29415f; border-radius: 5px; min-height: 28px; }}
QProgressBar {{ background: #07101c; border: 1px solid {LINE}; border-radius: 5px; text-align: center; }}
QProgressBar::chunk {{ background: {CYAN}; border-radius: 4px; }}
QGroupBox {{ border: 1px solid {LINE}; border-radius: 10px; margin-top: 14px; padding-top: 12px; }}
QGroupBox::title {{ color: {CYAN}; subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
"""


PHASE_TWO_STYLE += r"""
# Premium voice-first dashboard
QWidget#appShell { background: #03060e; }
QLabel#brandLabel { color: #f4f1ff; font-size: 16px; font-weight: 760; }
QLabel#railStatus { color: #55e39d; font-size: 11px; padding: 4px 0 8px 2px; }
QLabel#railSection { color: #6e7790; font-size: 9px; font-weight: 720; letter-spacing: 1.2px; }
QFrame#navigationRail { background: #080c18; border: 1px solid #1c2140; border-radius: 14px; }
QFrame#navigationRail QPushButton { background: #0a1020; border: 1px solid #151d35; border-radius: 9px; padding: 9px 10px; text-align: left; color: #dfe6f5; }
QFrame#navigationRail QPushButton:hover { background: #121933; border-color: #704cff; }
QFrame#navigationRail QPushButton:checked { background: #171331; border-color: #a65cff; color: #ffffff; }
QWidget#voiceFirstDashboard { background: #03060e; }
QFrame#dashboardRail, QWidget#dashboardRail { background: transparent; }
QFrame#systemStateCard, QFrame#focusCard, QFrame#contextCard, QFrame#shortcutsCard, QFrame#madeForYouCard, QFrame#trustSafetyCard, QFrame#memoryCard, QFrame#capabilitiesCard, QFrame#liveActivityCard, QFrame#currentActionCard {
    background: #090e1b; border: 1px solid #1a2140; border-radius: 13px;
}
QLabel#cardEyebrow { color: #9ba4bb; font-size: 10px; font-weight: 720; letter-spacing: .4px; }
QLabel#cardValue { color: #f5f3ff; font-size: 13px; font-weight: 720; }
QLabel#cardDetail { color: #7f89a3; font-size: 10px; line-height: 1.3; }
QLabel#greetingTitle { color: #f7f5ff; font-size: 26px; font-weight: 760; }
QLabel#greetingSubtitle { color: #8993ab; font-size: 12px; }
QFrame#voiceWorkspace { background: #060a15; border: 1px solid #171d37; border-radius: 16px; }
QFrame#voiceOrb { background: transparent; border: none; }
QLabel#orbState { color: #f6efff; font-size: 22px; font-weight: 760; letter-spacing: .8px; }
QPushButton#modePill, QCheckBox#modePill { background: #0a1020; border: 1px solid #262b4e; border-radius: 15px; padding: 8px 12px; color: #d9d8e9; }
QPushButton#modePill:hover, QCheckBox#modePill:hover { border-color: #9d57ff; }
QCheckBox#modePill::indicator { width: 0px; height: 0px; }
QLabel#modePillLabel { color: #c8b8ff; background: #0b1020; border: 1px solid #32295e; border-radius: 15px; padding: 8px 12px; }
QLabel#cardTitle { color: #f0eefe; font-size: 11px; font-weight: 720; }
QLabel#currentAction { color: #818aa2; font-size: 11px; }
QTextEdit#conversationTranscript { background: #060a14; border: 1px solid #171d34; border-radius: 10px; padding: 8px; color: #dde4f1; }
QLineEdit#conversationInput { background: #070c18; border: 1px solid #202744; border-radius: 19px; padding: 10px 14px; color: #e9edf7; }
QPushButton#sendButton { background: #6f38ff; border: 1px solid #995dff; border-radius: 19px; min-width: 40px; min-height: 30px; font-size: 16px; }
QPushButton#sendButton:hover { background: #7e49ff; }
QPushButton#dangerButton { background: #0a1020; border: 1px solid #3c2c57; border-radius: 16px; padding: 8px 11px; color: #c9b7d8; }
QPushButton#dangerButton:enabled:hover { border-color: #ff5c75; color: #ffe5ea; }
QFrame#capabilityTile { background: #0a1020; border: 1px solid #171f39; border-radius: 9px; }
QLabel#tileName { color: #ced6e6; font-size: 9px; font-weight: 620; }
QLabel#viewAll { color: #8f78c6; font-size: 9px; padding-top: 3px; }

"""
