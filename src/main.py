"""
src/main.py

DEBATE NIGHT — Main Entry Point
================================
Set MY_PERSONA below, then run:

    PERSONA=trump python src/main.py
    PERSONA=biden python src/main.py

On startup, a GUI lets you select:
  - 🎭 XTTS Voice Clone (pre-generated, zero latency)
  - ⚡ Azure Neural TTS (real-time, always works)

Keyboard controls during debate:
  SPACE  — Force opening statement (first speaker only)
  M      — Moderator interjects with new topic
  F      — Toggle fact-checker on/off
  C      — Trigger crowd reaction manually
  R      — Reset conversation history
  ESC    — End debate
"""

import sys
import os

# ── SET THIS PER LAPTOP ────────────────────────────────────────────────────────
# Mac/Linux:         PERSONA=trump python src/main.py
# Windows CMD:       set PERSONA=trump && python src/main.py
# Windows PowerShell: $env:PERSONA="trump"; python src/main.py
MY_PERSONA = os.environ.get("PERSONA", "trump")   # "trump" or "biden"
# ──────────────────────────────────────────────────────────────────────────────

# AI imports BEFORE PyQt6 to avoid DLL conflicts on Windows
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Cross-platform helpers
from src.utils.platform import enable_windows_console_colors, print_platform_info
enable_windows_console_colors()   # no-op on Mac/Linux

from src.brain.model import DebateBrain
from src.brain.fact_checker import FactChecker
from src.audio.listener import DebateListener
from src.audio.xtts_speaker import DualSpeaker      # handles both XTTS + Azure
from src.audio.sound_effects import SoundEffectsEngine
from src.moderator.siskind import SiskindModerator

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QKeyEvent

from src.gui.dashboard import DebateDashboard
from src.gui.voice_selector import VoiceModeSelector


# ══════════════════════════════════════════════════════════════════════════════
#  DEBATE WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class DebateWorker(QThread):
    """
    Background thread: Listen → Think (with RAG) → Speak → repeat.
    Communicates with GUI via Qt signals.
    """

    sig_start_speaking  = pyqtSignal(str, str)       # (persona, text)
    sig_stop_speaking   = pyqtSignal(str)             # (persona,)
    sig_set_listening   = pyqtSignal(str)             # (persona,)
    sig_set_thinking    = pyqtSignal(str)             # (persona,)
    sig_fact_check      = pyqtSignal(str, str, str)  # (verdict, claim, real_stat)
    sig_ticker          = pyqtSignal(str)             # (message,)

    def __init__(self, persona: str, voice_mode: str):
        super().__init__()
        self.persona = persona
        self.voice_mode = voice_mode
        self._running = True
        self._force_speak = False
        self._moderator_interject = False
        self._pending_prompt = None

        print(f"\n🚀 Initializing Debate Night")
        print(f"   Persona     : {persona.upper()}")
        print(f"   Voice mode  : {voice_mode.upper()}")

        # ── AI Brain (with RAG) ────────────────────────────────────────────────
        self.brain = DebateBrain(persona)

        # ── Voice — DualSpeaker handles XTTS + Azure fallback ─────────────────
        self.speaker = DualSpeaker(persona, mode=voice_mode)

        # ── Siskind moderator voice follows selected mode (XTTS/Azure fallback)
        self._siskind_speaker = DualSpeaker("siskind", mode=voice_mode)
        self.moderator = SiskindModerator(tts_callback=self._siskind_speak)

        # ── STT, Sound FX, Fact Checker ───────────────────────────────────────
        self.ears    = DebateListener()
        self.sfx     = SoundEffectsEngine()
        self.checker = FactChecker()

        print(f"✅ All systems ready.\n")
        self.sig_ticker.emit(f"SYSTEM READY | Voice: {voice_mode.upper()} | RAG: {'ON' if self.brain.rag_stats()['ready'] else 'OFF'}")

    # ── Main Loop ──────────────────────────────────────────────────────────────

    def run(self):
        # Opening: Siskind introduces the debate
        self.moderator.open_debate()
        self._pending_prompt = self.moderator.introduce_topic()

        while self._running:
            try:
                self._debate_turn()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[Main Loop Error] {e}")
                import traceback
                traceback.print_exc()

    def _debate_turn(self):
        # ── 1. Listen ─────────────────────────────────────────────────────────
        self.sig_set_listening.emit(self.persona)

        if self._moderator_interject:
            self._moderator_interject = False
            self._pending_prompt = self.moderator.introduce_topic()
            return

        if self._force_speak:
            self._force_speak = False
            opponent_text = "Please give your opening statement for this presidential debate."
        elif self._pending_prompt:
            opponent_text = self._pending_prompt
            self._pending_prompt = None
            self.sig_ticker.emit(f"MODERATOR: {opponent_text}")
        else:
            opponent_text = self.ears.listen_for_turn()

        if not opponent_text:
            return

        # ── 2. Think (Brain + RAG) ─────────────────────────────────────────────
        self.sig_set_thinking.emit(self.persona)
        self.sig_ticker.emit(f"OPPONENT: {opponent_text}")

        reply = self.brain.generate_response(opponent_text)

        # Log RAG stats occasionally
        stats = self.brain.rag_stats()
        if stats["ready"] and self.brain.turn_count % 5 == 0:
            self.sig_ticker.emit(
                f"RAG: {stats['hits']} hits / {stats['misses']} misses | "
                f"corpus: {stats['corpus_size']} quotes"
            )

        # ── 3. Fact-check opponent async ───────────────────────────────────────
        self.checker.check_async(opponent_text, "opponent", self._on_fact_check_result)

        # ── 4. Speak ──────────────────────────────────────────────────────────
        words = len(reply.split())
        self.ears.mute_for(words / 2.5 + 2.0)   # echo suppression

        self.sig_start_speaking.emit(self.persona, reply)
        self.sfx.react_to_speech(reply, self.persona)
        self.speaker.speak(reply)
        self.sig_stop_speaking.emit(self.persona)

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_fact_check_result(self, result: dict):
        verdict   = result.get("verdict", "UNVERIFIABLE")
        claim     = result.get("claim", "")
        real_stat = result.get("real_stat", "")
        self.sig_fact_check.emit(verdict, claim, real_stat)
        if verdict in ("FALSE", "MISLEADING"):
            self.sfx.play_fact_check_fail()
        elif verdict == "TRUE":
            self.sfx.play_fact_check_pass()
        self.sig_ticker.emit(f"FACT CHECK [{verdict}]: {claim[:60]}...")

    def _siskind_speak(self, text: str):
        if not text:
            return
        # Avoid hearing our own moderator output as opponent microphone input.
        words = len(text.split())
        self.ears.mute_for(words / 2.5 + 1.5)
        self.sig_start_speaking.emit("siskind", text)
        self._siskind_speaker.speak(text)
        self.sig_stop_speaking.emit("siskind")

    # ── Controls ───────────────────────────────────────────────────────────────

    def force_speak(self):     self._force_speak = True
    def trigger_moderator(self): self._moderator_interject = True
    def stop(self):            self._running = False


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class DebateApp:
    """Wires together: voice selector → GUI → worker thread."""

    def __init__(self, persona: str):
        self.app = QApplication(sys.argv)
        self.persona = persona
        self.worker = None
        self.gui = None

        # ── Step 1: Show voice mode selector ──────────────────────────────────
        self.selector = VoiceModeSelector(persona)
        self.selector.mode_selected.connect(self._on_mode_selected)
        self.selector.show()

    def _on_mode_selected(self, mode: str):
        """Called when user picks XTTS or Azure on the startup screen."""
        print(f"\n🎬 Voice mode selected: {mode.upper()}")

        # ── Step 2: Launch main debate GUI ────────────────────────────────────
        self.gui = DebateDashboard(my_persona=self.persona)
        self.gui.show()

        # ── Step 3: Start worker thread ────────────────────────────────────────
        self.worker = DebateWorker(self.persona, mode)

        self.worker.sig_start_speaking.connect(self.gui.start_speaking)
        self.worker.sig_stop_speaking.connect(self.gui.stop_speaking)
        self.worker.sig_set_listening.connect(self.gui.set_listening)
        self.worker.sig_set_thinking.connect(self.gui.set_thinking)
        self.worker.sig_fact_check.connect(self.gui.show_fact_check)
        self.worker.sig_ticker.connect(self.gui.add_ticker_message)

        self.gui.keyPressEvent = self._on_key_press
        self.worker.start()

        print(f"✅ Debate started! SPACE=speak  M=moderator  F=fact-check  ESC=quit\n")

    def _on_key_press(self, event: QKeyEvent):
        if self.worker is None:
            return
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.worker.force_speak()
        elif key == Qt.Key.Key_M:
            self.worker.trigger_moderator()
        elif key == Qt.Key.Key_F:
            enabled = self.worker.checker.toggle()
            self.gui.add_ticker_message(f"FACT CHECKER: {'ON' if enabled else 'OFF'}")
        elif key == Qt.Key.Key_C:
            self.worker.sfx.play("applause", volume=0.6)
        elif key == Qt.Key.Key_R:
            self.worker.brain.reset()
            self.gui.add_ticker_message("DEBATE RESET — NEW ROUND STARTING")
        elif key == Qt.Key.Key_Escape:
            self.worker.stop()
            self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if MY_PERSONA not in ("trump", "biden"):
        print(f"❌ Invalid persona '{MY_PERSONA}'. Set PERSONA=trump or PERSONA=biden")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║         🏛️  AI PRESIDENTIAL DEBATE NIGHT  🏛️                ║
║             Purdue University — Spring 2026                  ║
║       ECE49595NL / ECE59500NL — NLP Assignment 1            ║
╠══════════════════════════════════════════════════════════════╣
║  Persona  : {MY_PERSONA.upper():<48} ║
║  Features : GPT-4 Brain | RAG | Voice Clone | Fact Checker  ║
║  Controls : SPACE=speak  M=moderator  F=facts  ESC=quit     ║
╚══════════════════════════════════════════════════════════════╝
""")

    app = DebateApp(MY_PERSONA)
    app.run()
