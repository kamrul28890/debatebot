"""
src/gui/dashboard.py

Dual-laptop live dashboard:
- Local candidate panel (large)
- Anonymous user moderator panel (small)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.utils.platform import comic_font, impact_font, monospace_font, serif_font


logger = logging.getLogger(__name__)

_IMPACT = impact_font()
_MONO = monospace_font()
_COMIC = comic_font()
_SERIF = serif_font()

COLORS = {
    "bg": "#0f1115",
    "stage": "#1a1f27",
    "stage_floor": "#11161d",
    "line": "#2e3a49",
    "gold": "#f0c35f",
    "text": "#f3f5f8",
    "muted": "#aeb8c8",
    "trump": "#c63a3a",
    "biden": "#355ec6",
    "moderator": "#0d1016",
    "ticker_bg": "#0a0e14",
    "ticker_text": "#f6d27f",
}


class ScrollingTicker(QLabel):
    """Bottom ticker for live transcript and system notes."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"""
            background-color: {COLORS['ticker_bg']};
            color: {COLORS['ticker_text']};
            font-family: {_MONO};
            font-size: 13px;
            font-weight: 700;
            padding: 0 10px;
            border-top: 1px solid {COLORS['line']};
            """
        )
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self._messages = [
            "DUAL LAPTOP LIVE DEBATE",
            "AUDIO-FIRST TURN SYNC | LAN FALLBACK ENABLED",
            "FACT CHECK OVERLAY ENABLED",
        ]
        self._text = "  |  ".join(self._messages) + "  |  "
        self._cursor = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(35)

    def add_message(self, text: str) -> None:
        clean = " ".join((text or "").split())
        if clean:
            self._text += f"{clean.upper()}  |  "

    def _scroll(self) -> None:
        if not self._text:
            return

        self._cursor = (self._cursor + 2) % (len(self._text) * 8)
        start = self._cursor // 8

        metrics = QFontMetrics(self.font())
        avg_char = max(1, metrics.horizontalAdvance("A"))
        visible = max(40, int(self.width() / avg_char) + 6)

        chunk = self._text[start : start + visible]
        if len(chunk) < visible:
            chunk += self._text[: visible - len(chunk)]
        self.setText(chunk)


class StatusPill(QLabel):
    STATES = {
        "idle": ("#3f4754", "STANDBY"),
        "listening": ("#2c8f5e", "LISTENING"),
        "thinking": ("#ad7c29", "THINKING"),
        "speaking": ("#b33b3b", "SPEAKING"),
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(156, 28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state = "idle"
        self._blink_visible = True

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)

        self.set_state("idle")

    def set_state(self, state: str) -> None:
        self._state = state if state in self.STATES else "idle"
        color, text = self.STATES[self._state]
        self.setText(text)
        self.setStyleSheet(
            f"""
            background-color: {color};
            color: white;
            border-radius: 14px;
            font-size: 10px;
            font-weight: 800;
            font-family: {_MONO};
            """
        )

        if self._state in {"listening", "thinking"}:
            self._blink_timer.start(550)
        else:
            self._blink_timer.stop()
            self._blink_visible = True
            self.setVisible(True)

    def _blink(self) -> None:
        self._blink_visible = not self._blink_visible
        self.setVisible(self._blink_visible)


class CandidatePanel(QFrame):
    """Single speaker panel with avatar, bubble, and status."""

    def __init__(
        self,
        persona_key: str,
        display_name: str,
        accent: str,
        anonymous_style: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.persona_key = persona_key
        self.display_name = display_name
        self.accent = accent
        self.anonymous_style = anonymous_style

        panel_bg_top = "#171e27" if not anonymous_style else "#06080d"
        panel_bg_bottom = COLORS["stage_floor"] if not anonymous_style else "#0b0f16"

        self.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {panel_bg_top}, stop:1 {panel_bg_bottom});
                border: 2px solid {accent};
                border-radius: 10px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel(display_name.upper())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"""
            background-color: {accent};
            color: white;
            font-size: 14px;
            font-weight: 900;
            font-family: {_IMPACT};
            padding: 6px;
            border-radius: 6px;
            letter-spacing: 1px;
            """
        )
        layout.addWidget(title)

        self.avatar = QLabel()
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(170)
        self.avatar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.avatar)

        self.speech_bubble = QLabel("...")
        self.speech_bubble.setWordWrap(True)
        self.speech_bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble_bg = "#f6f7fb" if not anonymous_style else "#171d28"
        bubble_text = "#111111" if not anonymous_style else "#dbe4f3"
        self.speech_bubble.setStyleSheet(
            f"""
            background-color: {bubble_bg};
            color: {bubble_text};
            border: 2px solid {accent};
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 13px;
            font-family: {_COMIC};
            font-weight: 700;
            min-height: 58px;
            """
        )
        layout.addWidget(self.speech_bubble)

        row = QHBoxLayout()
        row.addStretch()
        self.status_pill = StatusPill()
        row.addWidget(self.status_pill)
        row.addStretch()
        layout.addLayout(row)

        self._frames = self._load_frames()
        self.avatar.setPixmap(self._frames["idle"])

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._toggle_mouth)
        self._frame_idx = 0
        self._talk_frames = [
            self._frames["talking"],
            self._frames["idle"],
            self._frames["talking"],
            self._frames["idle"],
        ]

    def _load_frames(self) -> dict[str, QPixmap]:
        if self.anonymous_style:
            idle = self._build_anonymous_avatar(highlight=False)
            talking = self._build_anonymous_avatar(highlight=True)
            listening = self._build_anonymous_avatar(highlight=False)
            return {"idle": idle, "talking": talking, "listening": listening}

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(base_dir, "data", f"raw_{self.persona_key}")

        return {
            "idle": self._load_pixmap(os.path.join(data_dir, "idle.png"), "#5a6370"),
            "talking": self._load_pixmap(os.path.join(data_dir, "talking.png"), "#5a6370"),
            "listening": self._load_pixmap(os.path.join(data_dir, "listening.png"), "#5a6370"),
        }

    def _build_anonymous_avatar(self, highlight: bool = False) -> QPixmap:
        pix = QPixmap(190, 190)
        pix.fill(QColor("#080b11"))

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ring_color = QColor("#253243" if not highlight else "#364b66")
        painter.setPen(QPen(ring_color, 4))
        painter.drawEllipse(8, 8, 174, 174)

        shadow = QColor("#07090d")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(50, 36, 90, 90)
        painter.drawRoundedRect(42, 108, 106, 58, 18, 18)

        if highlight:
            painter.setBrush(QColor("#99adc7"))
            painter.drawEllipse(86, 76, 18, 18)

        painter.end()
        return pix

    @staticmethod
    def _load_pixmap(path: str, fallback: str) -> QPixmap:
        if os.path.exists(path):
            return QPixmap(path).scaled(
                190,
                190,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        placeholder = QPixmap(190, 190)
        placeholder.fill(QColor(fallback))
        return placeholder

    def set_speaking(self, text: str = "") -> None:
        self.status_pill.set_state("speaking")
        if text:
            self.speech_bubble.setText(f'"{text}"')
        self._anim_timer.start(120)

    def set_listening(self) -> None:
        self.status_pill.set_state("listening")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["listening"])

    def set_thinking(self) -> None:
        self.status_pill.set_state("thinking")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["idle"])

    def set_idle(self) -> None:
        self.status_pill.set_state("idle")
        self._anim_timer.stop()
        self.avatar.setPixmap(self._frames["idle"])

    def _toggle_mouth(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(self._talk_frames)
        self.avatar.setPixmap(self._talk_frames[self._frame_idx])


class FactCheckOverlay(QFrame):
    """Overlay banner for fact-check verdicts."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.hide()
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(4, 6, 10, 0.95);
                border: 3px solid #c64f4f;
                border-radius: 12px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self.verdict_label = QLabel("FACT CHECK")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verdict_label.setStyleSheet(
            f"color: #f06a6a; font-size: 24px; font-weight: 900; font-family: {_IMPACT};"
        )
        layout.addWidget(self.verdict_label)

        self.claim_label = QLabel()
        self.claim_label.setWordWrap(True)
        self.claim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.claim_label.setStyleSheet(f"color: #ffd58f; font-size: 14px; font-family: {_SERIF};")
        layout.addWidget(self.claim_label)

        self.stat_label = QLabel()
        self.stat_label.setWordWrap(True)
        self.stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stat_label.setStyleSheet(f"color: #e8eef8; font-size: 14px; font-family: {_MONO};")
        layout.addWidget(self.stat_label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_result(self, verdict: str, claim: str, real_stat: str) -> None:
        palette = {
            "FALSE": ("#ff5a5a", "FACT CHECK - FALSE"),
            "MISLEADING": ("#f3a445", "FACT CHECK - MISLEADING"),
            "TRUE": ("#4dd084", "FACT CHECK - TRUE"),
            "UNVERIFIABLE": ("#9aa4b4", "FACT CHECK - UNVERIFIABLE"),
        }
        color, label = palette.get(verdict, palette["UNVERIFIABLE"])

        self.verdict_label.setText(label)
        self.verdict_label.setStyleSheet(
            f"color: {color}; font-size: 24px; font-weight: 900; font-family: {_IMPACT};"
        )
        self.claim_label.setText(f'"{claim}"')
        self.stat_label.setText(f"REFERENCE: {real_stat}")
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgba(4, 6, 10, 0.95);
                border: 3px solid {color};
                border-radius: 12px;
            }}
            """
        )

        self.show()
        self._hide_timer.start(8500)


class DebateDashboard(QWidget):
    """Main live debate window for one local candidate + moderator."""

    sig_back_requested = pyqtSignal()

    def __init__(self, local_persona: str = "trump", module_label: str = ""):
        super().__init__()
        self.local_persona = local_persona if local_persona in {"trump", "biden"} else "trump"
        self.remote_persona = "biden" if self.local_persona == "trump" else "trump"
        self.module_label = module_label or "AZURE + ROBOTIC VOICE | DUAL-LAPTOP LIVE"
        self._sync_state = "searching"

        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("DebateBot - Dual Laptop Live Debate")
        self.resize(1220, 760)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        stage = QWidget()
        stage.setStyleSheet(f"background-color: {COLORS['stage']};")
        stage_layout = QHBoxLayout(stage)
        stage_layout.setContentsMargins(10, 10, 10, 6)
        stage_layout.setSpacing(10)

        local_name = "Donald J. Trump" if self.local_persona == "trump" else "Joe Biden"
        local_color = COLORS["trump"] if self.local_persona == "trump" else COLORS["biden"]

        self.local_panel = CandidatePanel(self.local_persona, local_name, local_color)
        self.moderator_panel = CandidatePanel(
            "moderator_user",
            "You (Moderator)",
            COLORS["moderator"],
            anonymous_style=True,
        )
        self.moderator_panel.setMinimumWidth(240)
        self.moderator_panel.setMaximumWidth(310)

        stage_layout.addWidget(self.local_panel, stretch=7)
        stage_layout.addWidget(self.moderator_panel, stretch=3)
        root.addWidget(stage, stretch=1)

        self.fact_overlay = FactCheckOverlay(stage)
        self.fact_overlay.setGeometry(44, 44, stage.width() - 88, 220)
        stage.resizeEvent = lambda e: self.fact_overlay.setGeometry(44, 44, e.size().width() - 88, 220)

        self.fact_status_label = QLabel("FACT CHECK: STANDBY")
        self.fact_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fact_status_label.setStyleSheet(
            "QLabel { background-color: #0f151e; color: #f2d289; border-top: 1px solid #2a3340; "
            "border-bottom: 1px solid #2a3340; padding: 6px; font-size: 12px; font-weight: 700; }"
        )
        root.addWidget(self.fact_status_label)

        self.ticker = ScrollingTicker()
        root.addWidget(self.ticker)

        self._panel_map = {
            self.local_persona: self.local_panel,
            "moderator": self.moderator_panel,
            "moderator_user": self.moderator_panel,
            "siskind": self.moderator_panel,
        }

        self._apply_panel_glow(self.local_panel, "#cc6c6c" if self.local_persona == "trump" else "#6c93cc")
        self._apply_panel_glow(self.moderator_panel, "#5a6678")

        self.moderator_panel.set_listening()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(46)

        left_color = COLORS["trump"] if self.local_persona == "trump" else COLORS["biden"]
        header.setStyleSheet(
            f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {left_color},
                stop:0.5 #11161f,
                stop:1 #11161f
            );
            border-bottom: 2px solid {COLORS['gold']};
            """
        )

        row = QHBoxLayout(header)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(8)

        back_btn = QPushButton("Back To Modes")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #151b24;
                color: #f4f6f9;
                border: 1px solid #566071;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #1f2a39; }
            QPushButton:pressed { background-color: #121b27; }
            """
        )
        back_btn.clicked.connect(self.sig_back_requested.emit)
        row.addWidget(back_btn)

        live = QLabel("LIVE")
        live.setStyleSheet(f"color: #ff6c6c; font-size: 14px; font-weight: 900; font-family: {_IMPACT};")
        row.addWidget(live)

        local_mode = QLabel(f"LOCAL: {self.local_persona.upper()}")
        local_mode.setStyleSheet(
            """
            QLabel {
                color: #d7e2f2;
                background-color: rgba(10, 14, 20, 0.85);
                border: 1px solid #60738c;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-family: Courier New, monospace;
                font-weight: 700;
            }
            """
        )
        row.addWidget(local_mode)

        module_label = QLabel(self.module_label.upper())
        module_label.setStyleSheet(
            """
            QLabel {
                color: #d7e2f2;
                background-color: rgba(10, 14, 20, 0.85);
                border: 1px solid #60738c;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-family: Courier New, monospace;
                font-weight: 700;
            }
            """
        )
        row.addWidget(module_label)

        self.sync_status_label = QLabel("LAN SEARCHING")
        self.sync_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_status_label.setMinimumWidth(180)
        row.addWidget(self.sync_status_label)
        self.set_sync_status("searching", "LAN FAILSAFE SEARCHING")

        row.addStretch()

        title = QLabel("AI PRESIDENTIAL DEBATE")
        title.setStyleSheet(
            f"color: {COLORS['gold']}; font-size: 16px; font-weight: 900; font-family: {_IMPACT};"
        )
        row.addWidget(title)

        row.addStretch()

        self.clock_label = QLabel("")
        self.clock_label.setStyleSheet(f"color: #ffffff; font-size: 13px; font-family: {_MONO};")
        row.addWidget(self.clock_label)

        timer = QTimer(self)
        timer.timeout.connect(self._update_clock)
        timer.start(1000)
        self._update_clock()

        return header

    @staticmethod
    def _apply_panel_glow(panel: QWidget, color: str) -> None:
        glow = QGraphicsDropShadowEffect(panel)
        glow.setBlurRadius(24)
        glow.setXOffset(0)
        glow.setYOffset(0)
        glow.setColor(QColor(color))
        panel.setGraphicsEffect(glow)

    def _panel_for(self, persona: str) -> CandidatePanel | None:
        return self._panel_map.get(persona)

    def start_speaking(self, persona: str, text: str) -> None:
        panel = self._panel_for(persona)
        if panel is not None:
            panel.set_speaking(text)

        label = self._display_name(persona)
        self.ticker.add_message(f"{label}: {text}")

    def stop_speaking(self, persona: str) -> None:
        panel = self._panel_for(persona)
        if panel is not None:
            panel.set_idle()

    def set_listening(self, persona: str) -> None:
        panel = self._panel_for(persona)
        if panel is not None:
            panel.set_listening()

    def set_thinking(self, persona: str) -> None:
        panel = self._panel_for(persona)
        if panel is not None:
            panel.set_thinking()

    def show_fact_check(self, verdict: str, claim: str, real_stat: str) -> None:
        self.fact_overlay.show_result(verdict, claim, real_stat)
        self.fact_status_label.setText(f"FACT CHECK [{verdict}] {real_stat}")

        color = "#f2d289"
        if verdict == "TRUE":
            color = "#5cd38f"
        elif verdict in ("FALSE", "MISLEADING"):
            color = "#ff7676"

        self.fact_status_label.setStyleSheet(
            "QLabel { background-color: #0f151e; border-top: 1px solid #2a3340; "
            f"border-bottom: 1px solid #2a3340; padding: 6px; font-size: 12px; font-weight: 700; color: {color}; }}"
        )

    def add_ticker_message(self, text: str) -> None:
        self.ticker.add_message(text)

    def set_sync_status(self, state: str, detail: str) -> None:
        state_key = (state or "searching").lower().strip()
        palette = {
            "connected": ("#1a2c22", "#79d49f", "LAN CONNECTED"),
            "searching": ("#2d2414", "#f0c56a", "LAN SEARCHING"),
            "disabled": ("#222834", "#9aa7bc", "LAN OFF"),
            "error": ("#351818", "#ef8a8a", "LAN ERROR"),
        }
        bg, fg, default_text = palette.get(state_key, palette["searching"])
        label_text = default_text if not detail else detail.upper()
        self.sync_status_label.setText(label_text)
        self.sync_status_label.setStyleSheet(
            f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                border: 1px solid #60738c;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-family: {_MONO};
                font-weight: 700;
            }}
            """
        )
        self._sync_state = state_key

    def _display_name(self, persona: str) -> str:
        names = {
            self.local_persona: self.local_persona.upper(),
            self.remote_persona: f"{self.remote_persona.upper()} (REMOTE)",
            "moderator": "MODERATOR",
            "moderator_user": "MODERATOR",
            "siskind": "MODERATOR",
        }
        return names.get(persona, persona.upper())

    def _update_clock(self) -> None:
        self.clock_label.setText(datetime.now().strftime("%I:%M:%S %p"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DebateDashboard(local_persona="trump", module_label="AZURE + ROBOTIC VOICE | DUAL-LAPTOP LIVE")
    win.show()
    sys.exit(app.exec())
