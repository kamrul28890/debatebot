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
    QGraphicsDropShadowEffect, QFrame, QSizePolicy
)
from PyQt6.QtGui import (
    QPixmap, QFont, QColor, QPainter, QPen, QBrush,
    QLinearGradient, QPalette, QFontDatabase
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, pyqtSignal, QThread

from src.utils.platform import impact_font, monospace_font, comic_font, serif_font

logger = logging.getLogger(__name__)

# ── Resolve fonts once at import time ─────────────────────────────────────────
_IMPACT   = impact_font()
_MONO     = monospace_font()
_COMIC    = comic_font()
_SERIF    = serif_font()


# ── Color Palette (South Park political parody) ────────────────────────────────
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
        self.setFixedHeight(36)
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
            "🏛️ AI PRESIDENTIAL DEBATE 2026  |  PURDUE UNIVERSITY ECE DEPT  |  ",
            "⚡ POWERED BY GPT-4 & AZURE NEURAL TTS  |  ",
            "🎓 MODERATED BY PROF. JEFFREY SISKIND  |  ",
            "📊 FACT-CHECKER ACTIVE  |  ALL CLAIMS VERIFIED IN REAL TIME  |  ",
        ]
        self._scroll_text = "  " + "  ★  ".join(self._messages) * 3
        self._pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(30)

    def add_message(self, text: str):
        self._scroll_text += f"  ●  {text.upper()}"

    def _scroll(self):
        self._pos = (self._pos + 2) % (len(self._scroll_text) * 8)
        # Use character clipping for scroll effect
        char_pos = self._pos // 8
        display = self._scroll_text[char_pos:char_pos + 80]
        self.setText(display)


class StatusPill(QLabel):
    """Animated status pill showing LISTENING / THINKING / SPEAKING."""

    STATES = {
        "idle":      ("#333333", "⏸  STANDBY"),
        "listening": ("#00aa55", "🎤  LISTENING"),
        "thinking":  ("#cc8800", "🧠  THINKING..."),
        "speaking":  ("#cc2200", "🗣️  SPEAKING"),
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

        # ── Name banner ────────────────────────────────────────────────────────
        name_label = QLabel(name.upper())
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(f"""
            background-color: {color};
            color: white;
            font-size: 18px;
            font-weight: 900;
            font-family: {_IMPACT};
            padding: 6px;
            border-radius: 4px;
            letter-spacing: 3px;
        """)
        layout.addWidget(name_label)

        # ── Avatar image ───────────────────────────────────────────────────────
        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(280)
        self.avatar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.avatar)

        # ── Speech bubble ──────────────────────────────────────────────────────
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

        # ── Status pill ────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        status_row.addStretch()
        self.status_pill = StatusPill()
        status_row.addWidget(self.status_pill)
        status_row.addStretch()
        layout.addLayout(status_row)

        # ── Load avatar images ─────────────────────────────────────────────────
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(base_dir, "data", f"raw_{persona}")

        self._frames = {
            "idle":      self._load_pixmap(os.path.join(data_dir, "idle.png")),
            "talking":   self._load_pixmap(os.path.join(data_dir, "talking.png")),
            "listening": self._load_pixmap(os.path.join(data_dir, "listening.png")),
        }
        self.avatar.setPixmap(self._frames["idle"])

        # ── Mouth animation ────────────────────────────────────────────────────
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
                260, 280,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        # Return a colored placeholder if image missing
        placeholder = QPixmap(260, 280)
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

        # ── Verdict badge ──────────────────────────────────────────────────────
        self.verdict_label = QLabel("FACT CHECK ❌")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verdict_label.setStyleSheet(f"""
            color: #ff0000;
            font-size: 22px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 4px;
        """)
        layout.addWidget(self.verdict_label)

        # ── Claim ──────────────────────────────────────────────────────────────
        self.claim_label = QLabel()
        self.claim_label.setWordWrap(True)
        self.claim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.claim_label.setStyleSheet(f"""
            color: #ffcc00;
            font-size: 13px;
            font-style: italic;
            font-family: {_SERIF};
        """)
        layout.addWidget(self.claim_label)

        # ── Divider ────────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #555555; margin: 4px 0;")
        layout.addWidget(divider)

        # ── Real stat ──────────────────────────────────────────────────────────
        self.stat_label = QLabel()
        self.stat_label.setWordWrap(True)
        self.stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stat_label.setStyleSheet(f"""
            color: #ffffff;
            font-size: 14px;
            font-weight: bold;
            font-family: {_MONO};
        """)
        layout.addWidget(self.stat_label)

        # ── Source note ────────────────────────────────────────────────────────
        self.source_label = QLabel("— GPT-4 Fact Checker")
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.source_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.source_label)

        # ── Auto-hide timer ────────────────────────────────────────────────────
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        # ── Flash animation ────────────────────────────────────────────────────
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash)
        self._flash_count = 0

    def show_result(self, verdict: str, claim: str, real_stat: str):
        """Display a fact-check result."""
        verdict_configs = {
            "FALSE":       ("#ff0000", "FACT CHECK  ❌  FALSE"),
            "MISLEADING":  ("#ff8800", "⚠️  MISLEADING"),
            "TRUE":        ("#00cc44", "✅  VERIFIED TRUE"),
            "UNVERIFIABLE":("#888888", "🔍  UNVERIFIABLE"),
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
        self.stat_label.setText(f"📊 {real_stat}")

        self.show()
        self._hide_timer.start(6000)  # hide after 6 seconds

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
    - (none — worker calls methods directly via Qt signals)
    
    Public slots (call from any thread via signals):
    - start_speaking(persona, text)
    - stop_speaking(persona)
    - set_listening(persona)
    - set_thinking(persona)
    - show_fact_check(verdict, claim, real_stat)
    - add_ticker_message(text)
    """

    def __init__(self, my_persona: str):
        super().__init__()
        self.my_persona = my_persona
        self._setup_window()
        self._build_ui()

    # ── Window setup ───────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("🏛️ AI PRESIDENTIAL DEBATE 2026 — PURDUE UNIVERSITY")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ─────────────────────────────────────────────────────────
        header = self._build_header()
        root.addWidget(header)

        # ── Main stage ─────────────────────────────────────────────────────────
        stage_container = QWidget()
        stage_container.setStyleSheet(f"background-color: {COLORS['bg']};")
        stage_layout = QHBoxLayout(stage_container)
        stage_layout.setContentsMargins(16, 16, 16, 8)
        stage_layout.setSpacing(12)

        self.trump_panel = CandidatePanel("trump", "Donald J. Trump", COLORS["trump_banner"])
        self.biden_panel = CandidatePanel("biden", "Joe Biden", COLORS["biden_banner"])

        # Siskind moderator — smaller center panel
        self.siskind_panel = CandidatePanel("siskind", "Prof. Siskind", COLORS["siskind_bg"])
        self.siskind_panel.setMaximumWidth(200)

        stage_layout.addWidget(self.trump_panel, stretch=3)
        stage_layout.addWidget(self.siskind_panel, stretch=2)
        stage_layout.addWidget(self.biden_panel, stretch=3)

        root.addWidget(stage_container, stretch=1)

        # ── Fact-check overlay (absolute positioned) ───────────────────────────
        self.fact_overlay = FactCheckOverlay(stage_container)
        self.fact_overlay.setGeometry(80, 80, stage_container.width() - 160, 180)

        # Resize overlay when window resizes
        stage_container.resizeEvent = lambda e: self.fact_overlay.setGeometry(
            80, 80, e.size().width() - 160, 200
        )

        # ── Ticker ─────────────────────────────────────────────────────────────
        self.ticker = ScrollingTicker()
        root.addWidget(self.ticker)

        # ── Initial state ──────────────────────────────────────────────────────
        self._set_my_panel_listening()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(52)
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

        # Left: live badge
        live = QLabel("🔴 LIVE")
        live.setStyleSheet(f"""
            color: #ff4444;
            font-size: 14px;
            font-weight: 900;
            font-family: {_IMPACT};
            letter-spacing: 2px;
        """)
        hlayout.addWidget(live)
        hlayout.addStretch()

        # Center: title
        title = QLabel("🏛️  AI PRESIDENTIAL DEBATE 2026  🏛️")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            color: {COLORS['gold']};
            font-size: 20px;
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

    # ── Public slots (called from worker thread via Qt signals) ────────────────

    def start_speaking(self, persona: str, text: str):
        panel = self._get_panel(persona)
        if panel:
            panel.set_speaking(text[:100] + "..." if len(text) > 100 else text)
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

    def add_ticker_message(self, text: str):
        self.ticker.add_message(text)

    # ── Internal helpers ───────────────────────────────────────────────────────

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

    def _update_clock(self):
        now = datetime.now().strftime("%I:%M:%S %p")
        self.clock_label.setText(f"⏱ {now}")

    def keyPressEvent(self, event):
        """Keyboard shortcuts for debate control."""
        key = event.key()
        # These get handled by main.py via a signal — we just pass the key
        logger.debug("[GUI] Key pressed: %s", key)
        super().keyPressEvent(event)


# ── Standalone test ────────────────────────────────────────────────────────────
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
            "Look folks, here's the deal — this GUI is no malarkey. Not a joke."))
        QTimer.singleShot(10000, lambda: win.show_fact_check(
            "FALSE",
            "We had the greatest economy in the history of our country.",
            "GDP growth averaged 2.5% under Trump, lower than Obama's 2.9% peak. (BLS, 2021)"
        ))
        QTimer.singleShot(10000, lambda: win.start_speaking("siskind",
            "Gentlemen, I've graded worse arguments. Moving on."))

    demo()
    sys.exit(app.exec())
