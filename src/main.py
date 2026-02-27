"""
src/main.py

Application entry point for Debate Night.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

# Keep startup output clean on all platforms.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Some Windows environments fail to load torch after Qt is initialized.
# Best-effort preload before importing PyQt keeps Qwen/XTTS stable.
try:
    import torch  # noqa: F401
    TORCH_PRELOAD_ERROR = ""
except Exception as exc:
    TORCH_PRELOAD_ERROR = str(exc)

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

# Allow `python src/main.py` while keeping package-safe imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio.listener import DebateListener
from src.audio.sound_effects import SoundEffectsEngine
from src.audio.xtts_speaker import DualSpeaker
from src.brain.fact_checker import FactChecker
from src.brain.model import DebateBrain
from src.cache.deterministic import ensure_script, script_fingerprint
from src.gui.dashboard import DebateDashboard
from src.gui.voice_selector import DebateModeSelector
from src.moderator.siskind import SiskindModerator
from src.utils.logging_utils import setup_logging
from src.utils.platform import enable_windows_console_colors


logger = logging.getLogger(__name__)
MY_PERSONA = os.environ.get("PERSONA", "trump")


enable_windows_console_colors()


def module_label(brain_mode: str, voice_mode: str, run_mode: str) -> str:
    brain = "QWEN" if brain_mode == "qwen" else "AZURE"
    voice = "VOICE CLONING" if voice_mode == "xtts" else "ROBOTIC VOICE"
    run = "CACHED" if run_mode == "cached" else "LIVE"
    return f"{brain} + {voice} | {run}"


class DebateWorker(QThread):
    """Background debate loop thread."""

    sig_start_speaking = pyqtSignal(str, str)
    sig_stop_speaking = pyqtSignal(str)
    sig_set_listening = pyqtSignal(str)
    sig_set_thinking = pyqtSignal(str)
    sig_fact_check = pyqtSignal(str, str, str)
    sig_ticker = pyqtSignal(str)

    def __init__(
        self,
        persona: str,
        voice_mode: str,
        brain_type: str = "azure",
        run_mode: str = "live",
        module_name: str = "",
    ):
        super().__init__()
        self.persona = persona
        self.voice_mode = voice_mode
        self.brain_type = brain_type
        self.run_mode = run_mode if run_mode in ("live", "cached") else "live"
        self.module_name = module_name or module_label(brain_type, voice_mode, self.run_mode)

        self._running = True
        self._force_speak = False
        self._moderator_interject = False
        self._pending_prompt: str | None = None
        self._cleaned_up = False
        self._startup_messages: list[str] = []
        self._cached_lines: list[str] = []
        self._cached_index = 0
        self._cached_script: dict = {}
        if TORCH_PRELOAD_ERROR:
            self._startup_messages.append(f"Torch preload warning: {TORCH_PRELOAD_ERROR}")

        logger.info(
            "Initializing worker persona=%s brain=%s voice=%s mode=%s",
            persona,
            brain_type,
            voice_mode,
            self.run_mode,
        )

        self.brain = DebateBrain(persona, brain_type=brain_type)
        if self.brain.brain_type != brain_type:
            self._startup_messages.append(
                f"Brain fallback active: requested {brain_type.upper()}, running {self.brain.brain_type.upper()}"
            )
            if getattr(self.brain, "qwen_init_error", None):
                self._startup_messages.append(f"Reason: {self.brain.qwen_init_error}")
        self.brain_type = self.brain.brain_type

        self.speaker = DualSpeaker(persona, mode=voice_mode)
        self._siskind_speaker = DualSpeaker("siskind", mode=voice_mode)
        if voice_mode == "xtts" and self.speaker.mode != "xtts":
            self._startup_messages.append("Voice fallback active: XTTS unavailable, using Azure TTS.")
        self.moderator = SiskindModerator(tts_callback=self._siskind_speak)

        self.ears = DebateListener()
        self.sfx = SoundEffectsEngine()
        self.checker = FactChecker()

        rag_ready = self.brain.rag_stats()["ready"]
        self._startup_messages.insert(
            0,
            "SYSTEM READY | Module: "
            f"{self.module_name} | Brain: "
            f"{self.brain_type.upper()} | Voice: {self.speaker.mode.upper()} | "
            f"RAG: {'ON' if rag_ready else 'OFF'} | MODE: {self.run_mode.upper()}",
        )

    def run(self) -> None:
        try:
            for msg in self._startup_messages:
                self.sig_ticker.emit(msg)

            if self.run_mode == "cached":
                self._initialize_cached_mode()

            self.moderator.open_debate()
            self._pending_prompt = self.moderator.introduce_topic()

            while self._running:
                try:
                    self._debate_turn()
                except KeyboardInterrupt:
                    break
                except Exception:
                    logger.exception("Worker loop error")
        finally:
            self._cleanup_once()

    def _debate_turn(self) -> None:
        if not self._running:
            return

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

        if not self._running or not opponent_text:
            return

        self.sig_set_thinking.emit(self.persona)
        self.sig_ticker.emit(f"OPPONENT: {opponent_text}")

        if self.run_mode == "cached":
            reply = self._next_cached_response(opponent_text)
        else:
            reply = self.brain.generate_response(opponent_text)
        reply = self._format_turn_text(reply)
        if not self._running:
            return

        stats = self.brain.rag_stats()
        if stats["ready"] and self.brain.turn_count % 5 == 0:
            self.sig_ticker.emit(
                f"RAG: {stats['hits']} hits / {stats['misses']} misses | "
                f"corpus: {stats['corpus_size']} quotes"
            )

        self.checker.check_async(opponent_text, "opponent", self._on_fact_check_result)

        if not self._running:
            return

        words = len(reply.split())
        self.ears.mute_for(words / 2.5 + 2.0)

        self.sig_start_speaking.emit(self.persona, reply)
        self.sfx.react_to_speech(reply, self.persona)
        try:
            self.speaker.speak(reply)
        except Exception:
            logger.exception("Primary speaker failure")
            self.sig_ticker.emit("Voice output error on primary speaker.")
        self.sig_stop_speaking.emit(self.persona)

    def _on_fact_check_result(self, result: dict) -> None:
        if not self._running:
            return

        verdict = result.get("verdict", "UNVERIFIABLE")
        claim = result.get("claim", "")
        real_stat = result.get("real_stat", "")

        self.sig_fact_check.emit(verdict, claim, real_stat)

        if verdict in ("FALSE", "MISLEADING"):
            self.sfx.play_fact_check_fail()
        elif verdict == "TRUE":
            self.sfx.play_fact_check_pass()

        self.sig_ticker.emit(f"FACT CHECK [{verdict}]: {claim[:60]}...")

    def _siskind_speak(self, text: str) -> None:
        if not text or not self._running:
            return

        text = self._format_turn_text(text)
        words = len(text.split())
        self.ears.mute_for(words / 2.5 + 1.5)
        self.sig_start_speaking.emit("siskind", text)
        try:
            self._siskind_speaker.speak(text)
        except Exception:
            logger.exception("Siskind speaker failure")
            self.sig_ticker.emit("Voice output error on moderator channel.")
        self.sig_stop_speaking.emit("siskind")

    def _initialize_cached_mode(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.sig_ticker.emit("CACHE: loading deterministic script...")
        try:
            self._cached_script = ensure_script(base_dir)
        except Exception as exc:
            logger.warning("Cached mode script load failed: %s", exc)
            self.sig_ticker.emit(f"CACHE: failed to load script ({exc}) - using live generation")
            self.run_mode = "live"
            return

        self._cached_lines = list(self._cached_script.get(self.persona, []))
        self._cached_index = 0

        if not self._cached_lines:
            self.sig_ticker.emit("CACHE: no lines found for persona - using live generation")
            self.run_mode = "live"
            return

        self.sig_ticker.emit(
            f"CACHE: loaded {len(self._cached_lines)} deterministic turns for {self.persona.upper()}"
        )
        try:
            fingerprint = script_fingerprint(self._cached_script)[:12]
            self.sig_ticker.emit(f"CACHE: session sync fingerprint {fingerprint}")
        except Exception:
            pass

        if self.speaker.mode == "xtts" and self.speaker.xtts_speaker is not None:
            coverage = self.speaker.estimate_cache_coverage(self._cached_lines)
            if coverage < 0.99:
                self.sig_ticker.emit(
                    "CACHE: XTTS audio cache incomplete. Run 'Prepare Cache For Selected Module' for zero-latency playback."
                )

    def _next_cached_response(self, opponent_text: str) -> str:
        if self._cached_index < len(self._cached_lines):
            line = self._cached_lines[self._cached_index]
            self._cached_index += 1
            return line

        self.sig_ticker.emit("Cached script exhausted; switching to live generation.")
        self.run_mode = "live"
        return self.brain.generate_response(opponent_text)

    @staticmethod
    def _format_turn_text(
        text: str,
        target_words: int = 50,
        min_words: int = 40,
        max_words: int = 55,
        hard_cap: int = 70,
    ) -> str:
        """
        Keep turns around target length while preserving sentence boundaries.
        """
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return ""

        words = cleaned.split()
        if len(words) <= max_words:
            return cleaned

        # Try sentence-aware clipping first.
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
        if sentences:
            selected: list[str] = []
            count = 0
            for sentence in sentences:
                wc = len(sentence.split())
                if count + wc <= max_words:
                    selected.append(sentence)
                    count += wc
                    continue

                # If we already have enough content, stop before overflow.
                if count >= min_words:
                    break

                # Otherwise allow one sentence overflow up to hard_cap so we end cleanly.
                if count + wc <= hard_cap:
                    selected.append(sentence)
                    count += wc
                break

            if selected:
                merged = " ".join(selected).strip()
                merged_words = len(merged.split())
                if min_words <= merged_words <= hard_cap:
                    return merged

        # Fallback: find punctuation close to target within first hard_cap words.
        window = " ".join(words[:hard_cap])
        best_end = -1
        best_delta = 10_000
        for match in re.finditer(r"[.!?](?:['\")\]]+)?(?:\s|$)", window):
            fragment = window[: match.end()].strip()
            wc = len(fragment.split())
            if wc < min_words:
                continue
            delta = abs(wc - target_words)
            if delta < best_delta:
                best_delta = delta
                best_end = match.end()
        if best_end > 0:
            return window[:best_end].strip()

        # Last resort: keep it readable without abrupt comma/semicolon ending.
        clipped = " ".join(words[:max_words]).rstrip(" ,;:")
        if clipped and clipped[-1] not in ".!?":
            clipped += "."
        return clipped

    def force_speak(self) -> None:
        self._force_speak = True

    def trigger_moderator(self) -> None:
        self._moderator_interject = True

    def stop(self) -> None:
        """Graceful cooperative stop for UI back/exit actions."""
        if not self._running:
            return

        self._running = False
        self._force_speak = False
        self._moderator_interject = False
        self._pending_prompt = None
        self._cleanup_once()

    def _cleanup_once(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True

        try:
            self.moderator.stop_timer()
        except Exception:
            pass

        try:
            self.checker.enabled = False
        except Exception:
            pass

        try:
            self.ears.stop()
        except Exception:
            pass

        try:
            self.speaker.stop()
        except Exception:
            pass

        try:
            self._siskind_speaker.stop()
        except Exception:
            pass

        try:
            if self.brain_type == "qwen" and hasattr(self.brain, "qwen_brain"):
                self.brain.qwen_brain.unload_model()
        except Exception:
            pass


class DebateApp:
    """Wire selector, dashboard, and background worker."""

    def __init__(self, persona: str):
        self.app = QApplication(sys.argv)
        self.persona = persona
        self.worker: DebateWorker | None = None
        self.gui: DebateDashboard | None = None
        self.selector: DebateModeSelector | None = None

        self.app.aboutToQuit.connect(self._on_app_quit)
        self._show_mode_selector()

    def _show_mode_selector(self) -> None:
        if self.selector is not None:
            self.selector.close()

        self.selector = DebateModeSelector(self.persona)
        self.selector.mode_selected.connect(self._on_mode_selected)
        self.selector.show()

    def _on_mode_selected(self, persona: str, brain_mode: str, voice_mode: str, run_mode: str) -> None:
        self.persona = persona
        os.environ["PERSONA"] = persona
        mod_label = module_label(brain_mode, voice_mode, run_mode)

        logger.info(
            "Mode selection persona=%s brain=%s voice=%s run=%s",
            persona,
            brain_mode,
            voice_mode,
            run_mode,
        )

        if self.selector is not None:
            self.selector.close()

        self.gui = DebateDashboard(my_persona=self.persona, module_label=mod_label)
        self.gui.sig_back_requested.connect(self._return_to_mode_selector)
        self.gui.keyPressEvent = self._on_key_press
        self.gui.show()

        try:
            self.worker = DebateWorker(
                self.persona,
                voice_mode,
                brain_type=brain_mode,
                run_mode=run_mode,
                module_name=mod_label,
            )
        except Exception as exc:
            logger.exception("Worker initialization failed")
            QMessageBox.critical(
                self.gui,
                "Startup Error",
                f"Failed to initialize selected module.\n\n{exc}",
            )
            self.gui.close()
            self.gui = None
            self._show_mode_selector()
            return

        self.worker.sig_start_speaking.connect(self.gui.start_speaking)
        self.worker.sig_stop_speaking.connect(self.gui.stop_speaking)
        self.worker.sig_set_listening.connect(self.gui.set_listening)
        self.worker.sig_set_thinking.connect(self.gui.set_thinking)
        self.worker.sig_fact_check.connect(self.gui.show_fact_check)
        self.worker.sig_ticker.connect(self.gui.add_ticker_message)
        self.worker.start()

    def _stop_worker(self) -> None:
        if self.worker is None:
            return

        self.worker.stop()

        # Allow cooperative shutdown first.
        if not self.worker.wait(5000):
            logger.warning("Worker did not stop in 5s; forcing terminate")
            self.worker.terminate()
            self.worker.wait(1000)

        self.worker = None

    def _return_to_mode_selector(self) -> None:
        logger.info("Returning to selector")
        self._stop_worker()

        if self.gui is not None:
            self.gui.close()
            self.gui = None

        self._show_mode_selector()

    def _on_key_press(self, event: QKeyEvent) -> None:
        if self.worker is None:
            return

        key = event.key()

        if key == Qt.Key.Key_Space:
            self.worker.force_speak()
        elif key == Qt.Key.Key_M:
            self.worker.trigger_moderator()
        elif key == Qt.Key.Key_F:
            enabled = self.worker.checker.toggle()
            if self.gui is not None:
                self.gui.add_ticker_message(f"FACT CHECKER: {'ON' if enabled else 'OFF'}")
        elif key == Qt.Key.Key_C:
            self.worker.sfx.play("applause", volume=0.6)
        elif key == Qt.Key.Key_R:
            self.worker.brain.reset()
            if self.gui is not None:
                self.gui.add_ticker_message("DEBATE RESET - NEW ROUND STARTING")
        elif key == Qt.Key.Key_Escape:
            self._stop_worker()
            self.app.quit()

    def _on_app_quit(self) -> None:
        self._stop_worker()

    def run(self) -> None:
        sys.exit(self.app.exec())


def main() -> int:
    setup_logging()

    if MY_PERSONA not in ("trump", "biden"):
        logger.error("Invalid persona '%s'. Set PERSONA=trump or PERSONA=biden", MY_PERSONA)
        return 1

    app = DebateApp(MY_PERSONA)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
