"""
src/gui/dashboard.py

South Park Parody Presidential Debate GUI.

Visual style:
- Paper-cutout cartoon aesthetic (flat colors, thick black outlines)
- Split screen: Trump left, Biden right
- Siskind moderator appears center as a smaller figure
- Scroll ticker at bottom (live transcript + commentary)
- Fact-check overlay flashes full-screen
- Crowd reaction meter (animated bar)
- Status indicator: LISTENING / THINKING / SPEAKING
- Color palette: red & blue political, yellow stage lights, black outlines
"""

import os
import logging
import random
import sys
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QGraphicsDropShadowEffect, QFrame, QSizePolicy, QPushButton
)
from PyQt6.QtGui import (
    QPixmap, QFont, QColor, QPainter, QPen, QBrush,
    QLinearGradient, QPalette, QFontDatabase, QFontMetrics
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, pyqtSignal, QThread

from src.utils.platform import impact_font, monospace_font, comic_font, serif_font

logger = logging.getLogger(__name__)

# â”€â”€ Resolve fonts once at import time â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_IMPACT   = impact_font()
_MONO     = monospace_font()
_COMIC    = comic_font()
_SERIF    = serif_font()


# â”€â”€ Color Palette (South Park political parody) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
COLORS = {
    "bg":            "#1a0a00",     # dark brown stage
    "stage_floor":   "#2d1a0a",     # wooden stage
    "trump_banner":  "#cc0000",     # republican red
    "biden_banner":  "#003399",     # democrat blue
    "gold":          "#ffd700",     # podium gold
    "white":         "#ffffff",
    "black":         "#000000",
    "ticker_bg":     "#0a0a0a",
    "ticker_text":   "#ffcc00",
    "fact_false":    "#ff0000",
    "fact_true":     "#00cc44",
    "fact_mislead":  "#ff8800",
    "status_listen": "#00ff88",
    "status_think":  "#ffaa00",
    "status_speak":  "#ff4444",
    "siskind_bg":    "#444444",
}


class ScrollingTicker(QLabel):
    """News ticker at the bottom that scrolls the debate transcript."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            background-color: {COLORS['ticker_bg']};
            color: {COLORS['ticker_text']};
            font-family: {_MONO};
            font-size: 14px;
            font-weight: bold;
            padding: 0 10px;
            border-top: 3px solid {COLORS['gold']};
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._messages = [
            "AI PRESIDENTIAL DEBATE 2026 | PURDUE UNIVERSITY ECE | ",
            "GPT-4 / QWEN BRAINS AVAILABLE | AZURE / XTTS VOICES AVAILABLE | ",
            "MODERATOR: PROF. JEFFREY SISKIND | FACT CHECKER ACTIVE | ",
        ]
        self._scroll_text = "  " + "  |  ".join(self._messages) * 3
        self._pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(30)

    def add_message(self, text: str):
        self._scroll_text += f"  -  {text.upper()}"

    def _scroll(self):
        self._pos = (self._pos + 2) % (len(self._scroll_text) * 8)
        # Use character clipping for scroll effect
        char_pos = self._pos // 8
        metrics = QFontMetrics(self.font())
        avg_char_width = max(1, metrics.horizontalAdvance("A"))
        visible_chars = max(50, int(self.width() / avg_char_width) + 8)
        display = self._scroll_text[char_pos:char_pos + visible_chars]
        if len(display) < visible_chars:
            display += self._scroll_text[: visible_chars - len(display)]
        self.setText(display)


class StatusPill(QLabel):
    """Animated status pill showing LISTENING / THINKING / SPEAKING."""

    STATES = {
        "idle": ("#333333", "STANDBY"),
        "listening": ("#00aa55", "LISTENING"),
        "thinking": ("#cc8800", "THINKING"),
        "speaking": ("#cc2200", "SPEAKING"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 30)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_visible = True
        self.set_state("idle")

    def set_state(self, state: str):
        self._state = state
        color, text = self.STATES.get(state, self.STATES["idle"])
        self.setText(text)
        self.setStyleSheet(f"""
            background-color: {color};
            color: white;
            border-radius: 15px;
            font-size: 11px;
            font-weight: bold;
            font-family: {_MONO};
        """)
        if state in ("listening", "thinking"):
            self._blink_timer.start(600)
        else:
            self._blink_timer.stop()
            self._blink_visible = True
            self.setVisible(True)

    def _blink(self):
        self._blink_visible = not self._blink_visible
        self.setVisible(self._blink_visible)


class CandidatePanel(QFrame):
    """
    One candidate's side of the debate stage.
    South Park paper-cutout style with animated mouth.
    """

    def __init__(self, persona: str, name: str, color: str, parent=None):
        super().__init__(parent)
        self.persona = persona
        self.name = name
        self.color = color

        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a1a0a, stop:1 {COLORS['stage_floor']}
                );
                border: 3px solid {color};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # â”€â”€ Name banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        name_label = QLabel(name.upper())
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(f"""
            background-color: {color};
            color: white;
            font-size: 14px;
            font-weight: 900;
            font-family: {_IMPACT};
            padding: 6px;
            border-radius: 4px;
            letter-spacing: 3px;
        """)
        layout.addWidget(name_label)

        # â”€â”€ Avatar image â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(150)
        self.avatar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.avatar)

        # â”€â”€ Speech bubble â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.speech_bubble = QLabel("...")
        self.speech_bubble.setWordWrap(True)
        self.speech_bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speech_bubble.setStyleSheet(f"""
            background-color: white;
            color: #111111;
            border: 3px solid {color};
            border-radius: 12px;
            padding: 10px 14px;
            font-size: 13px;
            font-family: {_COMIC};
            font-weight: bold;
            min-height: 60px;
        """)
        layout.addWidget(self.speech_bubble)

        # â”€â”€ Status pill â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        status_row = QHBoxLayout()
        status_row.addStretch()
        self.status_pill = StatusPill()
        status_row.addWidget(self.status_pill)
        status_row.addStretch()
        layout.addLayout(status_row)

        # â”€â”€ Load avatar images â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(base_dir, "data", f"raw_{persona}")

        self._frames = {
            "idle":      self._load_pixmap(os.path.join(data_dir, "idle.png")),
            "talking":   self._load_pixmap(os.path.join(data_dir, "talking.png")),
            "listening": self._load_pixmap(os.path.join(data_dir, "listening.png")),
        }
        self.avatar.setPixmap(self._frames["idle"])

        # â”€â”€ Mouth animation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._toggle_mouth)
        self._frame_index = 0
        self._talking_frames = [
            self._frames["talking"],
            self._frames["idle"],
            self._frames["talking"],
            self._frames["idle"],
        ]

    def set_speaking(self, text: str = ""):
        self.status_pill.set_state("speaking")
        if text:
            self.speech_bubble.setText(f'"{text}"')
        self._anim_timer.start(120)   # 120ms per frame = 8fps mouth flap

    def set_listening(self):
        self.status_pill.set_state("listening")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["listening"])

    def set_thinking(self):
        self.status_pill.set_state("thinking")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["idle"])

    def set_idle(self):
        self.status_pill.set_state("idle")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["idle"])

    def _toggle_mouth(self):
        self._frame_index = (self._frame_index + 1) % len(self._talking_frames)
        self.avatar.setPixmap(self._talking_frames[self._frame_index])

    @staticmethod
    def _load_pixmap(path: str) -> QPixmap:
        if os.path.exists(path):
            return QPixmap(path).scaled(
                190, 190,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        # Return a colored placeholder if image missing
        placeholder = QPixmap(190, 190)
        placeholder.fill(QColor("#555555"))
        return placeholder


class FactCheckOverlay(QFrame):
    """
    Full-width overlay that flashes when a lie is detected.
    Shows: verdict banner + claim + real stat.
    Auto-hides after 5 seconds.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.92);
                border: 4px solid #ff0000;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # â”€â”€ Verdict badge â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.verdict_label = QLabel("FACT CHECK")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verdict_label.setStyleSheet(f"""
            color: #ff0000;
            font-size: 28px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 4px;
        """)
        layout.addWidget(self.verdict_label)

        # â”€â”€ Claim â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.claim_label = QLabel()
        self.claim_label.setWordWrap(True)
        self.claim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.claim_label.setStyleSheet(f"""
            color: #ffcc00;
            font-size: 15px;
            font-style: italic;
            font-family: {_SERIF};
        """)
        layout.addWidget(self.claim_label)

        # â”€â”€ Divider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #555555; margin: 4px 0;")
        layout.addWidget(divider)

        # â”€â”€ Real stat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.stat_label = QLabel()
        self.stat_label.setWordWrap(True)
        self.stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stat_label.setStyleSheet(f"""
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            font-family: {_MONO};
        """)
        layout.addWidget(self.stat_label)

        # â”€â”€ Source note â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.source_label = QLabel("-- GPT-4 Fact Checker")
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.source_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.source_label)

        # â”€â”€ Auto-hide timer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        # â”€â”€ Flash animation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash)
        self._flash_count = 0

    def show_result(self, verdict: str, claim: str, real_stat: str):
        """Display a fact-check result."""
        verdict_configs = {
            "FALSE": ("#ff0000", "FACT CHECK - FALSE"),
            "MISLEADING": ("#ff8800", "FACT CHECK - MISLEADING"),
            "TRUE": ("#00cc44", "FACT CHECK - VERIFIED TRUE"),
            "UNVERIFIABLE": ("#888888", "FACT CHECK - UNVERIFIABLE"),
        }

        color, badge = verdict_configs.get(verdict, verdict_configs["UNVERIFIABLE"])

        self.verdict_label.setText(badge)
        self.verdict_label.setStyleSheet(f"""
            color: {color};
            font-size: 22px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 4px;
        """)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, 0.92);
                border: 4px solid {color};
                border-radius: 12px;
            }}
        """)

        self.claim_label.setText(f'"{claim}"')
        self.stat_label.setText(f"REFERENCE: {real_stat}")

        self.show()
        self._hide_timer.start(9000)  # keep visible longer

        # Flash 3 times
        self._flash_count = 0
        self._flash_timer.start(180)

    def _flash(self):
        self._flash_count += 1
        if self._flash_count > 6:
            self._flash_timer.stop()
            self.show()
            return
        if self._flash_count % 2 == 0:
            self.show()
        else:
            self.hide()


class DebateDashboard(QWidget):
    """
    Main debate GUI window.
    
    Signals emitted for use by DebateWorker thread:
    - (none â€” worker calls methods directly via Qt signals)
    
    Public slots (call from any thread via signals):
    - start_speaking(persona, text)
    - stop_speaking(persona)
    - set_listening(persona)
    - set_thinking(persona)
    - show_fact_check(verdict, claim, real_stat)
    - add_ticker_message(text)
    """
    sig_back_requested = pyqtSignal()

    def __init__(self, my_persona: str, module_label: str = ""):
        super().__init__()
        self.my_persona = my_persona
        self.module_label = module_label or "AZURE + ROBOTIC VOICE | LIVE"
        self._setup_window()
        self._build_ui()

    # â”€â”€ Window setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _setup_window(self):
        self.setWindowTitle("AI PRESIDENTIAL DEBATE 2026 - PURDUE UNIVERSITY")
        self.resize(1200, 750)
        self.setMinimumSize(620, 420)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

    # â”€â”€ UI construction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # â”€â”€ Header bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        header = self._build_header()
        root.addWidget(header)

        # â”€â”€ Main stage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        stage_container = QWidget()
        stage_container.setStyleSheet(f"background-color: {COLORS['bg']};")
        stage_layout = QHBoxLayout(stage_container)
        stage_layout.setContentsMargins(8, 8, 8, 4)
        stage_layout.setSpacing(8)

        self.trump_panel = CandidatePanel("trump", "Donald J. Trump", COLORS["trump_banner"])
        self.biden_panel = CandidatePanel("biden", "Joe Biden", COLORS["biden_banner"])

        # Siskind moderator â€” smaller center panel
        self.siskind_panel = CandidatePanel("siskind", "Prof. Siskind", COLORS["siskind_bg"])
        self.siskind_panel.setMinimumWidth(220)
        self.siskind_panel.setMaximumWidth(260)

        stage_layout.addWidget(self.trump_panel, stretch=4)
        stage_layout.addWidget(self.siskind_panel, stretch=3)
        stage_layout.addWidget(self.biden_panel, stretch=4)

        root.addWidget(stage_container, stretch=1)

        # â”€â”€ Fact-check overlay (absolute positioned) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.fact_overlay = FactCheckOverlay(stage_container)
        self.fact_overlay.setGeometry(40, 40, stage_container.width() - 80, 240)

        # Resize overlay when window resizes
        stage_container.resizeEvent = lambda e: self.fact_overlay.setGeometry(
            40, 40, e.size().width() - 80, 240
        )

        self.fact_status_label = QLabel("FACT CHECK: STANDBY")
        self.fact_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fact_status_label.setStyleSheet(
            "QLabel { background-color: #10151d; color: #ffd866; border-top: 1px solid #3a4656; "
            "border-bottom: 1px solid #3a4656; padding: 6px; font-size: 12px; font-weight: 700; }"
        )
        root.addWidget(self.fact_status_label)

        self.ticker = ScrollingTicker()
        root.addWidget(self.ticker)

        # â”€â”€ Initial state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._highlight_selected_persona()
        self._set_my_panel_listening()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {COLORS['trump_banner']},
                stop:0.45 #111111,
                stop:0.55 #111111,
                stop:1 {COLORS['biden_banner']}
            );
            border-bottom: 3px solid {COLORS['gold']};
        """)

        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(20, 0, 20, 0)

        back_btn = QPushButton("Back To Modes")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #1b1f25;
                color: #f5f7fa;
                border: 1px solid #606a78;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #273141;
            }
            QPushButton:pressed {
                background-color: #18222f;
            }
        """)
        back_btn.clicked.connect(self.sig_back_requested.emit)
        hlayout.addWidget(back_btn)

        # Left: live badge
        live = QLabel("LIVE")
        live.setStyleSheet(f"""
            color: #ff4444;
            font-size: 14px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 2px;
        """)
        hlayout.addWidget(live)

        persona_color = "#ffb3b3" if self.my_persona == "trump" else "#b6d4ff"
        persona_border = "#d35d5d" if self.my_persona == "trump" else "#5d87d3"
        persona_label = QLabel(f"PERSONA: {self.my_persona.upper()}")
        persona_label.setStyleSheet(f"""
            color: {persona_color};
            background-color: rgba(16, 22, 31, 0.8);
            border: 1px solid {persona_border};
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: bold;
            font-family: {_MONO};
            margin-left: 8px;
        """)
        hlayout.addWidget(persona_label)

        module_label = QLabel(self.module_label.upper())
        module_label.setStyleSheet(
            """
            QLabel {
                color: #d8e4f5;
                background-color: rgba(16, 22, 31, 0.8);
                border: 1px solid #5f7085;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
                font-family: Courier New, monospace;
                margin-left: 6px;
            }
            """
        )
        hlayout.addWidget(module_label)

        hlayout.addStretch()

        # Center: title
        title = QLabel("AI PRESIDENTIAL DEBATE 2026")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            color: {COLORS['gold']};
            font-size: 16px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 3px;
        """)
        hlayout.addWidget(title)
        hlayout.addStretch()

        # Right: clock
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(f"""
            color: white;
            font-size: 14px;
            font-family: {_MONO};
        """)
        hlayout.addWidget(self.clock_label)

        # Update clock every second
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)
        self._update_clock()

        return header

    # â”€â”€ Public slots (called from worker thread via Qt signals) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start_speaking(self, persona: str, text: str):
        panel = self._get_panel(persona)
        if panel:
            panel.set_speaking(text)
        self.ticker.add_message(f"{persona.upper()}: {text}")

    def stop_speaking(self, persona: str):
        panel = self._get_panel(persona)
        if panel:
            panel.set_idle()
        self._set_my_panel_listening()

    def set_listening(self, persona: str):
        panel = self._get_panel(persona)
        if panel:
            panel.set_listening()

    def set_thinking(self, persona: str):
        panel = self._get_panel(persona)
        if panel:
            panel.set_thinking()

    def show_fact_check(self, verdict: str, claim: str, real_stat: str):
        self.fact_overlay.show_result(verdict, claim, real_stat)
        self.fact_status_label.setText(f"FACT CHECK [{verdict}] {real_stat}")
        if verdict == "TRUE":
            color = "#2ecc71"
        elif verdict in ("FALSE", "MISLEADING"):
            color = "#ff6b6b"
        else:
            color = "#ffd866"
        self.fact_status_label.setStyleSheet(
            "QLabel { background-color: #10151d; border-top: 1px solid #3a4656; "
            f"border-bottom: 1px solid #3a4656; padding: 6px; font-size: 12px; font-weight: 700; color: {color}; }}"
        )

    def add_ticker_message(self, text: str):
        self.ticker.add_message(text)

    # â”€â”€ Internal helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_panel(self, persona: str) -> CandidatePanel:
        return {
            "trump": self.trump_panel,
            "biden": self.biden_panel,
            "siskind": self.siskind_panel,
        }.get(persona)

    def _set_my_panel_listening(self):
        panel = self._get_panel(self.my_persona)
        if panel:
            panel.set_listening()

    def _highlight_selected_persona(self):
        active = self._get_panel(self.my_persona)
        if active is None:
            return

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(28)
        glow.setXOffset(0)
        glow.setYOffset(0)
        glow.setColor(QColor("#ff7f7f" if self.my_persona == "trump" else "#7faeff"))
        active.setGraphicsEffect(glow)

    def _update_clock(self):
        now = datetime.now().strftime("%I:%M:%S %p")
        self.clock_label.setText(f"TIME {now}")

    def keyPressEvent(self, event):
        """Keyboard shortcuts for debate control."""
        key = event.key()
        # These get handled by main.py via a signal â€” we just pass the key
        logger.debug("[GUI] Key pressed: %s", key)
        super().keyPressEvent(event)


# â”€â”€ Standalone test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DebateDashboard("trump")
    win.show()

    # Demo sequence
    def demo():
        QTimer.singleShot(1000, lambda: win.start_speaking("trump",
            "Nobody builds debate UIs better than us. Tremendous. Believe me."))
        QTimer.singleShot(4000, lambda: win.stop_speaking("trump"))
        QTimer.singleShot(4500, lambda: win.set_thinking("biden"))
        QTimer.singleShot(6000, lambda: win.start_speaking("biden",
            "Look folks, here's the deal - this GUI is no malarkey. Not a joke."))
        QTimer.singleShot(10000, lambda: win.show_fact_check(
            "FALSE",
            "We had the greatest economy in the history of our country.",
            "GDP growth averaged 2.5% under Trump, lower than Obama's 2.9% peak. (BLS, 2021)"
        ))
        QTimer.singleShot(10000, lambda: win.start_speaking("siskind",
            "Gentlemen, I've graded worse arguments. Moving on."))

    demo()
    sys.exit(app.exec())
