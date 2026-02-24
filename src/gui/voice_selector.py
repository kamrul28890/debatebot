"""
src/gui/voice_selector.py

Startup screen: choose voice mode before the debate begins.

MODE A — XTTS Pre-Generated (Voice Cloning)
  - Uses Coqui XTTS v2 with ref.wav for voice cloning
  - Audio pre-generated offline and cached as WAV files
  - Zero latency during live debate (just plays cached audio)
  - Requires: TTS library, ref.wav files

MODE B — Azure Neural TTS (Live)  
  - Real-time Azure TTS with SSML prosody tuning
  - Sub-500ms latency
  - No setup beyond API key
  - Always available as fallback
"""

import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


COLORS = {
    "bg":       "#0d0d0d",
    "card":     "#1a1a1a",
    "border_a": "#ffd700",   # gold for XTTS
    "border_b": "#00aaff",   # blue for Azure
    "text":     "#ffffff",
    "subtext":  "#aaaaaa",
    "go_btn":   "#cc0000",
}


class ModeCard(QFrame):
    """Clickable mode selection card."""

    clicked = pyqtSignal(str)

    def __init__(self, mode: str, title: str, subtitle: str,
                 features: list, accent: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.accent = accent
        self._selected = False

        self.setFixedSize(340, 300)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            color: {accent};
            font-size: 20px;
            font-weight: 900;
            font-family: Impact, 'Arial Black', sans-serif;
            letter-spacing: 2px;
        """)
        layout.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel(subtitle)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 12px;")
        layout.addWidget(sub_lbl)

        layout.addSpacing(8)

        # Features
        for feat in features:
            row = QLabel(feat)
            row.setStyleSheet(f"color: {COLORS['text']}; font-size: 13px;")
            layout.addWidget(row)

        layout.addStretch()

        # Selected indicator
        self.indicator = QLabel("● SELECTED")
        self.indicator.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.indicator.setStyleSheet(f"""
            color: {accent};
            font-size: 11px;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        """)
        self.indicator.hide()
        layout.addWidget(self.indicator)

    def mousePressEvent(self, event):
        self.clicked.emit(self.mode)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style(selected)
        self.indicator.setVisible(selected)

    def _apply_style(self, selected: bool):
        border_width = 3 if selected else 1
        bg = "#222222" if selected else COLORS["card"]
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: {border_width}px solid {self.accent if selected else '#333333'};
                border-radius: 12px;
            }}
        """)


class VoiceModeSelector(QWidget):
    """
    Full-screen startup selector.
    Emits mode_selected(mode_str) when user clicks START.
    mode_str: "xtts" or "azure"
    """

    mode_selected = pyqtSignal(str)

    def __init__(self, persona: str):
        super().__init__()
        self.persona = persona
        self._selected_mode = "azure"   # safe default

        self.setWindowTitle("🏛️ Debate Night — Voice Mode")
        self.resize(800, 520)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

        self._build_ui()
        self._check_xtts_availability()  # Check availability and set default

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)

        # ── Header ─────────────────────────────────────────────────────────────
        header = QLabel("🏛️  SELECT VOICE MODE")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"""
            color: {COLORS['text']};
            font-size: 26px;
            font-weight: 900;
            font-family: Impact, 'Arial Black', sans-serif;
            letter-spacing: 4px;
        """)
        root.addWidget(header)

        sub = QLabel(f"Running as: {self.persona.upper()}  |  Purdue ECE49595NL — Spring 2026")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 13px;")
        root.addWidget(sub)

        root.addSpacing(10)

        # ── Cards ──────────────────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(30)
        cards_row.addStretch()

        self.card_xtts = ModeCard(
            mode="xtts",
            title="🎭  XTTS VOICE CLONE",
            subtitle="Pre-generated audio using Coqui XTTS v2.\nSounds like the real person.",
            features=[
                "✅  Cloned voice from ref.wav",
                "✅  Zero latency during debate",
                "✅  Most impressive for audience",
                "- Optional pre-generation for zero-latency cache",
                "- Auto-fallback to Azure if XTTS is unavailable",
            ],
            accent=COLORS["border_a"],
        )

        self.card_azure = ModeCard(
            mode="azure",
            title="⚡  AZURE NEURAL TTS",
            subtitle="Real-time Azure TTS with SSML prosody.\nAlways works, sub-500ms latency.",
            features=[
                "✅  Real-time, always reliable",
                "✅  SSML prosody (Trump louder, Biden softer)",
                "✅  No pre-generation needed",
                "✅  Instant fallback if XTTS fails",
                "○  Generic voice (not cloned)",
            ],
            accent=COLORS["border_b"],
        )

        self.card_xtts.clicked.connect(self._select_mode)
        self.card_azure.clicked.connect(self._select_mode)

        cards_row.addWidget(self.card_xtts)
        cards_row.addWidget(self.card_azure)
        cards_row.addStretch()
        root.addLayout(cards_row)


        root.addSpacing(10)

        # ── XTTS status note ───────────────────────────────────────────────────
        self.xtts_note = QLabel("")
        self.xtts_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.xtts_note.setStyleSheet(f"color: {COLORS['subtext']}; font-size: 11px;")
        self._check_xtts_availability()
        root.addWidget(self.xtts_note)

        # ── START button ───────────────────────────────────────────────────────
        self.start_btn = QPushButton("🚀  START DEBATE")
        self.start_btn.setFixedHeight(52)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['go_btn']};
                color: white;
                font-size: 18px;
                font-weight: 900;
                font-family: Impact, 'Arial Black', sans-serif;
                letter-spacing: 3px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #ee2222;
            }}
            QPushButton:pressed {{
                background-color: #aa0000;
            }}
        """)
        self.start_btn.clicked.connect(self._on_start)
        root.addWidget(self.start_btn)

    def _select_mode(self, mode: str):
        self._selected_mode = mode
        self.card_xtts.set_selected(mode == "xtts")
        self.card_azure.set_selected(mode == "azure")

    def _on_start(self):
        self.mode_selected.emit(self._selected_mode)
        self.close()

    def _check_xtts_availability(self):
        """Check if XTTS dependencies are available and show status."""
        issues = []
        base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        try:
            import torch  # noqa: F401
        except Exception:
            issues.append("torch missing")

        try:
            import torchaudio  # noqa: F401
        except Exception:
            issues.append("torchaudio missing")

        try:
            from TTS.api import TTS  # noqa: F401
        except Exception:
            issues.append("TTS missing")

        try:
            from src.audio.xtts_speaker import XTTS_AVAILABLE
            if not XTTS_AVAILABLE:
                issues.append("XTTS runtime unavailable")
        except Exception:
            issues.append("XTTS runtime unavailable")

        ref_wav = os.path.join(base, "data", f"raw_{self.persona}", "ref.wav")
        if not os.path.exists(ref_wav):
            issues.append(f"ref.wav missing for {self.persona}")

        cache_dir = os.path.join(base, "data", "xtts_cache", self.persona)
        cache_count = 0
        if os.path.isdir(cache_dir):
            cache_count = len([f for f in os.listdir(cache_dir) if f.endswith(".wav")])

        if issues:
            issue_text = ", ".join(issues)
            self.xtts_note.setText(
                f"XTTS unavailable: {issue_text} | install: pip install TTS torch torchaudio"
            )
            self.xtts_note.setStyleSheet("color: #ff8800; font-size: 11px;")
        else:
            cache_hint = f"{cache_count} cached clips" if cache_count else "no cache yet (live synthesis enabled)"
            self.xtts_note.setText(f"XTTS ready for {self.persona} - {cache_hint}.")
            self.xtts_note.setStyleSheet("color: #00cc66; font-size: 11px;")
            # Default to XTTS if available
            self._select_mode("xtts")


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)

    def on_mode(mode):
        print(f"Selected mode: {mode}")
        app.quit()

    selector = VoiceModeSelector("trump")
    selector.mode_selected.connect(on_mode)
    selector.show()

    sys.exit(app.exec())
