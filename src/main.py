"""
src/main.py

Application entry point for DebateBot (dual-laptop, live-only).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Keep startup output clean on all platforms.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Best-effort torch preload before Qt for stability in some environments.
try:
    import torch  # noqa: F401

    TORCH_PRELOAD_ERROR = ""
except Exception as exc:
    TORCH_PRELOAD_ERROR = str(exc)

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import DebateOrchestrator, RoundPlan
from src.gui.dashboard import DebateDashboard
from src.gui.voice_selector import DebateModeSelector
from src.infra import DebateMetrics
from src.services import DebateRuntime, LanSyncBus
from src.utils.logging_utils import setup_logging
from src.utils.platform import enable_windows_console_colors


logger = logging.getLogger(__name__)
enable_windows_console_colors()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, minimum: float = 0.1) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return default


def module_label(brain_mode: str, voice_mode: str) -> str:
    brain = "QWEN" if brain_mode == "qwen" else "AZURE"
    voice = "VOICE CLONING" if voice_mode == "xtts" else "ROBOTIC VOICE"
    return f"{brain} + {voice} | DUAL-LAPTOP LIVE"


@dataclass(frozen=True)
class ModeratorCue:
    prompt: str
    first_speaker: str
    round_id: str
    source: str
    ts: float
    listen_ms: float = 0.0


@dataclass(frozen=True)
class LocalTurnOutcome:
    text: str
    generate_ms: float
    speak_ms: float
    interrupted: bool = False
    interrupt_cue: ModeratorCue | None = None


class _NoopChecker:
    def __init__(self) -> None:
        self.enabled = False

    def check_async(self, statement: str, speaker: str, callback) -> None:
        return

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled


class _NoopSfx:
    def play(self, sound_name: str, volume: float = 0.7) -> None:
        return


class DebateWorker(QThread):
    """Dual-laptop candidate worker (local persona + moderator panel only)."""

    sig_start_speaking = pyqtSignal(str, str)
    sig_stop_speaking = pyqtSignal(str)
    sig_set_listening = pyqtSignal(str)
    sig_set_thinking = pyqtSignal(str)
    sig_fact_check = pyqtSignal(str, str, str)
    sig_ticker = pyqtSignal(str)
    sig_sync_status = pyqtSignal(str, str)

    def __init__(
        self,
        persona: str,
        voice_mode: str,
        brain_type: str = "azure",
        module_name: str = "",
    ):
        super().__init__()
        self.persona = persona if persona in {"trump", "biden"} else "trump"
        self.voice_mode = voice_mode
        self.requested_brain_type = brain_type
        self.module_name = module_name or module_label(brain_type, voice_mode)

        self._running = True
        self._cleaned_up = False
        self._startup_messages: list[str] = []

        fast_combo = self.requested_brain_type == "azure" and self.voice_mode == "azure"
        default_listen_timeout = 18 if fast_combo else 12
        self._listen_timeout_seconds = _env_int("DEBATE_LISTEN_TIMEOUT_SECONDS", default_listen_timeout)
        self._opponent_followup_timeout_seconds = _env_int("DEBATE_OPPONENT_FOLLOWUP_TIMEOUT_SECONDS", 4)
        self._opponent_end_confirm_timeout_seconds = _env_int("DEBATE_OPPONENT_END_CONFIRM_TIMEOUT_SECONDS", 3)
        self._min_opponent_turn_seconds = _env_float("DEBATE_MIN_OPPONENT_TURN_SECONDS", 12.0, minimum=0.0)
        self._opponent_finish_event_wait_seconds = _env_float(
            "DEBATE_OPPONENT_FINISH_EVENT_WAIT_SECONDS",
            2.5,
            minimum=0.0,
        )
        self._second_speaker_start_delay_seconds = _env_float(
            "DEBATE_SECOND_SPEAKER_START_DELAY_SECONDS",
            2.2,
            minimum=0.0,
        )
        self._moderator_echo_guard_seconds = _env_float("DEBATE_MODERATOR_ECHO_GUARD_SECONDS", 1.3, minimum=0.1)
        self._cue_sync_grace_seconds = _env_float("DEBATE_CUE_SYNC_GRACE_SECONDS", 0.8, minimum=0.05)
        self._interrupt_min_delay_seconds = _env_float("DEBATE_INTERRUPT_MIN_DELAY_SECONDS", 0.7, minimum=0.0)
        self._cue_coalesce_enabled = _env_bool("DEBATE_ENABLE_CUE_COALESCE", True)
        self._cue_coalesce_window_seconds = _env_float("DEBATE_CUE_COALESCE_WINDOW_SECONDS", 2.4, minimum=0.2)
        self._cue_coalesce_max_segments = _env_int("DEBATE_CUE_COALESCE_MAX_SEGMENTS", 2)
        # When enabled, non-moderator speech can start a synthetic round while waiting.
        # Keep this off by default to avoid auto-looping after a completed round.
        self._audio_resync_enabled = _env_bool("DEBATE_ENABLE_AUDIO_RESYNC", False)
        self._target_turn_seconds = _env_float("DEBATE_TARGET_SECONDS_PER_TURN", 30.0, minimum=10.0)
        self._speech_words_per_second = _env_float("DEBATE_WORDS_PER_SECOND", 2.1, minimum=1.0)
        self._max_turns_per_persona = _env_int("DEBATE_MAX_TURNS_PER_PERSONA", 8)

        target_words = max(45, int(round(self._target_turn_seconds * self._speech_words_per_second)))
        self._turn_min_words = max(35, target_words - 12)
        self._turn_max_words = max(self._turn_min_words + 6, target_words + 6)
        self._turn_hard_cap = self._turn_max_words + 10

        if TORCH_PRELOAD_ERROR:
            self._startup_messages.append(f"Torch preload warning: {TORCH_PRELOAD_ERROR}")

        self.runtime = DebateRuntime()
        self.orchestrator = DebateOrchestrator(max_turns_per_persona=self._max_turns_per_persona)
        self.metrics = DebateMetrics()

        # Audio remains primary; LAN metadata acts as a failsafe handoff/cue channel.
        self._lan_enabled = _env_bool("DEBATE_ENABLE_LAN_FAILSAFE", True)
        self._lan_takeover_delay_seconds = _env_float("DEBATE_LAN_CUE_TAKEOVER_DELAY_SECONDS", 1.2, minimum=0.0)
        self._lan_poll_timeout_seconds = _env_float("DEBATE_LAN_POLL_TIMEOUT_SECONDS", 8.0, minimum=0.5)
        self._lan_peer_timeout_seconds = _env_float("DEBATE_LAN_PEER_TIMEOUT_SECONDS", 6.0, minimum=1.0)
        self._sync_status_emit_interval_seconds = _env_float("DEBATE_SYNC_STATUS_EMIT_INTERVAL_SECONDS", 0.8, minimum=0.2)
        self.lan = LanSyncBus() if self._lan_enabled else None
        self._lan_backlog: list[dict] = []
        self._last_cue_ts = 0.0
        self._pending_cue: ModeratorCue | None = None
        self._last_round_finished_ts = 0.0
        self._recent_turn_texts: list[str] = []
        self._active_round_prompt = ""
        self._active_round_first_speaker = ""
        self._prefetched_opponent_segment = ""
        self._last_sync_status_key = ""
        self._last_sync_status_emit_at = 0.0

        self.checker = _NoopChecker()
        self.sfx = _NoopSfx()

    @property
    def remote_persona(self) -> str:
        return self.runtime.remote_persona

    def run(self) -> None:
        try:
            self._bootstrap_runtime()
            for msg in self._startup_messages:
                self.sig_ticker.emit(msg)

            self._run_dual_laptop_loop()
        except KeyboardInterrupt:
            logger.info("Worker interrupted")
        except Exception:
            logger.exception("Worker loop error")
            self.sig_ticker.emit("SYSTEM ERROR: debate worker crashed. Check logs.")
        finally:
            self._cleanup_once()

    def _bootstrap_runtime(self) -> None:
        self.sig_ticker.emit("BOOTSTRAP: initializing dual-laptop runtime...")
        started = time.monotonic()

        result = self.runtime.bootstrap(
            local_persona=self.persona,
            brain_type=self.requested_brain_type,
            voice_mode=self.voice_mode,
        )

        if self._lan_enabled and self.lan is not None:
            self.lan.start()
        self._emit_sync_status(force=True)

        if self.runtime.checker is not None:
            self.checker = self.runtime.checker
        if self.runtime.sfx is not None:
            self.sfx = self.runtime.sfx

        rag_ready = bool(self.runtime.brain and self.runtime.brain.rag_stats()["ready"])
        self._startup_messages.insert(
            0,
            "SYSTEM READY | Module: "
            f"{self.module_name} | Local Persona: {self.persona.upper()} | "
            f"Remote Persona: {self.remote_persona.upper()} | Brain: {result.active_brain_label.upper()} | "
            f"Voice: {self.voice_mode.upper()} | RAG: {'ON' if rag_ready else 'OFF/PARTIAL'} | MODE: DUAL-LAPTOP",
        )
        self._startup_messages.append(
            "SESSION PROFILE | "
            f"turns/persona: {self._max_turns_per_persona} | "
            f"target turn: ~{int(self._target_turn_seconds)}s "
            f"({self._turn_min_words}-{self._turn_max_words} words) | "
            f"listen timeout: {self._listen_timeout_seconds}s | "
            f"opponent follow-up: {self._opponent_followup_timeout_seconds}s | "
            f"end-confirm: {self._opponent_end_confirm_timeout_seconds}s | "
            f"min opponent turn: {self._min_opponent_turn_seconds:.0f}s | "
            f"finish-event wait: {self._opponent_finish_event_wait_seconds:.1f}s | "
            f"second-speaker delay: {self._second_speaker_start_delay_seconds:.1f}s | "
            f"moderator echo guard: {self._moderator_echo_guard_seconds:.1f}s | "
            f"cue coalesce: {self._cue_coalesce_window_seconds:.1f}s x{self._cue_coalesce_max_segments} | "
            f"LAN takeover delay: {self._lan_takeover_delay_seconds:.1f}s | "
            f"LAN poll timeout: {self._lan_poll_timeout_seconds:.1f}s"
        )
        if self._lan_enabled:
            self._startup_messages.append("SYNC POLICY: audio-primary + LAN metadata failsafe enabled.")
        else:
            self._startup_messages.append("SYNC POLICY: audio-only moderation/opponent detection; LAN sync disabled.")
        self._startup_messages.append(
            "AUDIO RESYNC: "
            + ("enabled (non-moderator speech may trigger synthetic round)." if self._audio_resync_enabled else "disabled (wait for explicit moderator cue).")
        )
        self._startup_messages.append(
            "CUE COALESCE: "
            + (
                f"enabled (buffer up to {self._cue_coalesce_max_segments} segment(s), "
                f"{self._cue_coalesce_window_seconds:.1f}s each)."
                if self._cue_coalesce_enabled
                else "disabled."
            )
        )
        self._startup_messages.extend(result.startup_messages)

        bootstrap_ms = (time.monotonic() - started) * 1000.0
        self._startup_messages.append(f"BOOTSTRAP COMPLETE: {bootstrap_ms:.0f}ms")
        logger.info("Worker bootstrap complete in %.0fms", bootstrap_ms)

    def _run_dual_laptop_loop(self) -> None:
        self.sig_ticker.emit(
            "USER MODERATOR: waiting for cue. Address Trump/Biden to choose first speaker; default is Trump."
        )

        while self._running and self.orchestrator.can_continue():
            cue = self._pending_cue
            self._pending_cue = None
            if cue is None:
                cue = self._wait_for_next_moderator_cue()
            if cue is None:
                continue

            plan = self._resolve_round_plan(cue)
            self.sig_start_speaking.emit("moderator", cue.prompt)
            self.sig_stop_speaking.emit("moderator")
            self.sig_ticker.emit(
                f"ROUND {cue.round_id}: first speaker={plan.first_speaker.upper()} source={cue.source.upper()}"
            )

            interrupted, interrupt_cue = self._run_round(plan, cue)
            if interrupted:
                if interrupt_cue is not None:
                    self._pending_cue = interrupt_cue
                continue

            if not self._running or not self.orchestrator.can_continue():
                break

            self.sig_set_listening.emit("moderator")
            self.sig_ticker.emit("USER MODERATOR: ask the next question.")
            time.sleep(0.08)

        self.sig_ticker.emit("DEBATE COMPLETE: dual-laptop session finished.")

    def _resolve_round_plan(self, cue: ModeratorCue) -> RoundPlan:
        plan = self.orchestrator.next_user_round(cue.prompt)
        forced_first = cue.first_speaker if cue.first_speaker in {"trump", "biden"} else plan.first_speaker
        if forced_first == plan.first_speaker:
            return plan

        forced_second = DebateOrchestrator.other_persona(forced_first)
        if not self.orchestrator.turn_available(forced_first):
            if self.orchestrator.turn_available(forced_second):
                forced_first, forced_second = forced_second, forced_first
            else:
                return plan

        self.sig_ticker.emit(f"ROUTING OVERRIDE: honoring detected starter {forced_first.upper()}.")
        return RoundPlan(
            moderator_prompt=cue.prompt,
            first_speaker=forced_first,
            second_speaker=forced_second,
        )

    def _wait_for_next_moderator_cue(self) -> ModeratorCue | None:
        ears = self.runtime.ears
        if ears is None:
            while self._running and self.orchestrator.can_continue():
                if self._lan_enabled:
                    event = self._take_lan_event(
                        lambda e: e.get("type") == "moderator_cue" and self._event_ts(e) > self._last_cue_ts
                    )
                    if event:
                        cue = self._cue_from_event(event, source="lan")
                        self._last_cue_ts = cue.ts
                        self.sig_ticker.emit("SYNC FALLBACK: accepted moderator cue from LAN.")
                        return cue
                time.sleep(0.1)
            return None

        while self._running and self.orchestrator.can_continue():
            self._emit_sync_status()
            # Brief guard right after a round to avoid trailing candidate audio
            # being mistaken for a new moderator cue.
            if self._last_round_finished_ts > 0:
                delta = time.time() - self._last_round_finished_ts
                if delta < self._moderator_echo_guard_seconds:
                    time.sleep(0.08)
                    continue

            if self._lan_enabled:
                takeover_event = self._take_lan_event(
                    lambda e: (
                        e.get("type") == "moderator_cue"
                        and self._event_ts(e) > self._last_cue_ts
                        and (time.time() - self._event_ts(e)) >= self._lan_takeover_delay_seconds
                    )
                )
                if takeover_event:
                    cue = self._cue_from_event(takeover_event, source="lan")
                    self._last_cue_ts = cue.ts
                    self.sig_ticker.emit("SYNC FALLBACK: accepted moderator cue from LAN.")
                    return cue

            self.sig_set_listening.emit("moderator")

            # Priority 1: audio capture.
            started = time.monotonic()
            timeout_seconds = self._listen_timeout_seconds
            if self._lan_enabled:
                timeout_seconds = min(timeout_seconds, self._lan_poll_timeout_seconds)
            heard = ears.listen_for_turn(timeout_seconds=timeout_seconds)
            listen_ms = (time.monotonic() - started) * 1000.0
            heard = " ".join((heard or "").split())
            if heard:
                is_startup_short = self._is_startup_short_topic_cue(heard)
                looks_moderator = self._looks_like_moderator_prompt(heard)
                if not (is_startup_short or looks_moderator):
                    if self._is_recent_turn_echo(heard):
                        self.sig_ticker.emit("Ignored candidate echo while waiting for moderator cue.")
                    elif self._audio_resync_enabled and self._looks_like_opponent_opening(heard):
                        self._prefetched_opponent_segment = heard
                        synthetic = self._cue_from_text(heard, source="audio_resync", listen_ms=listen_ms)
                        cue = ModeratorCue(
                            prompt=synthetic.prompt,
                            first_speaker=self.remote_persona,
                            round_id=synthetic.round_id,
                            source=synthetic.source,
                            ts=synthetic.ts,
                            listen_ms=synthetic.listen_ms,
                        )
                        self._last_cue_ts = cue.ts
                        self.sig_ticker.emit(
                            f"AUDIO RESYNC: inferred round from opponent speech ({self.remote_persona.upper()} first)."
                        )
                        return cue
                    else:
                        self.sig_ticker.emit("Ignored non-moderator audio; waiting for moderator cue.")
                    continue

                if self._is_transition_only_prompt(heard):
                    self.sig_ticker.emit("Moderator transition captured; waiting for addressed question...")
                    more_started = time.monotonic()
                    continuation = ears.listen_for_turn(timeout_seconds=self._opponent_followup_timeout_seconds)
                    continuation_ms = (time.monotonic() - more_started) * 1000.0
                    continuation = " ".join((continuation or "").split())
                    if continuation:
                        heard = f"{heard} {continuation}".strip()
                        listen_ms += continuation_ms
                    else:
                        self.sig_ticker.emit("Transition-only cue ignored; waiting for full moderator question.")
                        continue

                if self._cue_coalesce_enabled and not is_startup_short:
                    heard, coalesce_ms = self._coalesce_moderator_prompt(heard, ears)
                    if coalesce_ms > 0:
                        listen_ms += coalesce_ms

                cue = self._cue_from_text(heard, source="audio", listen_ms=listen_ms)
                self._publish_moderator_cue(cue)
                cue = self._harmonize_audio_cue(cue)
                self._last_cue_ts = cue.ts
                return cue

            if self._lan_enabled:
                # Priority 2: LAN fallback if no audio captured.
                event = self._take_lan_event(
                    lambda e: e.get("type") == "moderator_cue" and self._event_ts(e) > self._last_cue_ts
                )
                if event:
                    cue = self._cue_from_event(event, source="lan")
                    self._last_cue_ts = cue.ts
                    self.sig_ticker.emit("SYNC FALLBACK: accepted moderator cue from LAN.")
                    return cue

        return None

    def _run_round(self, plan, cue: ModeratorCue) -> tuple[bool, ModeratorCue | None]:
        round_started_at = time.time()
        self._active_round_prompt = cue.prompt
        self._active_round_first_speaker = plan.first_speaker
        prefetched_opponent_segment = " ".join((self._prefetched_opponent_segment or "").split())
        self._prefetched_opponent_segment = ""

        try:
            if plan.first_speaker == self.persona:
                outcome = self._speak_local_turn(
                    prompt=f"Moderator question: {cue.prompt}\n\nAnswer directly and clearly.",
                    round_id=cue.round_id,
                    round_started_at=round_started_at,
                    listen_ms=cue.listen_ms,
                )
                if outcome.interrupted:
                    return True, outcome.interrupt_cue

                self.orchestrator.begin_second_speaker()
                opponent_text, listen_ms, interrupt = self._wait_for_opponent_turn(
                    round_started_at=round_started_at,
                    expected_round_id=cue.round_id,
                    prefetched_segment="",
                )
                if interrupt is not None:
                    return True, interrupt
                if opponent_text:
                    self._record_remote_turn(opponent_text, listen_ms)

                self.orchestrator.finish_round()
                self._last_round_finished_ts = time.time()
                return False, None

            # Remote speaks first.
            opponent_text, listen_ms, interrupt = self._wait_for_opponent_turn(
                round_started_at=round_started_at,
                expected_round_id=cue.round_id,
                prefetched_segment=prefetched_opponent_segment,
            )
            if interrupt is not None:
                return True, interrupt
            if opponent_text:
                self._record_remote_turn(opponent_text, listen_ms)

            interrupt = self._sleep_until_second_speaker(round_started_at)
            if interrupt is not None:
                return True, interrupt

            self.orchestrator.begin_second_speaker()
            outcome = self._speak_local_turn(
                prompt=self._build_second_turn_prompt(cue.prompt, opponent_text),
                round_id=cue.round_id,
                round_started_at=round_started_at,
                listen_ms=0.0,
            )
            if outcome.interrupted:
                return True, outcome.interrupt_cue

            self.orchestrator.finish_round()
            self._last_round_finished_ts = time.time()
            return False, None
        finally:
            self._active_round_prompt = ""
            self._active_round_first_speaker = ""

    def _wait_for_opponent_turn(
        self,
        round_started_at: float,
        expected_round_id: str,
        prefetched_segment: str = "",
    ) -> tuple[str, float, ModeratorCue | None]:
        ears = self.runtime.ears
        if ears is None:
            return "", 0.0, None

        collected_segments: list[str] = []
        total_listen_ms = 0.0
        awaiting_end_confirmation = False
        first_speech_ts: float | None = None
        floor_notice_sent = False

        prefetched_clean = " ".join((prefetched_segment or "").split())
        if prefetched_clean:
            collected_segments.append(prefetched_clean)
            first_speech_ts = time.time()
            self.sig_ticker.emit("AUDIO RESYNC: captured opponent opener; waiting for full turn handoff.")

        while self._running and self.orchestrator.can_continue():
            self._emit_sync_status()
            cue = self._take_interrupt_cue(round_started_at)
            if cue is not None:
                self.sig_ticker.emit("INTERRUPT: new moderator cue received (LAN).")
                return "", 0.0, cue

            if self._lan_enabled:
                # Accept remote completion as authoritative handoff; round_id may differ
                # when both machines hear moderator audio independently.
                fallback = self._take_lan_event(
                    lambda e: (
                        e.get("type") == "speaker_finished"
                        and e.get("persona") == self.remote_persona
                        and self._event_ts(e) >= (round_started_at - 0.1)
                        and (
                            str(e.get("round_id", "")).strip() == expected_round_id
                            or bool(collected_segments)
                            or (
                                not collected_segments
                                and self._event_ts(e) >= (round_started_at + self._lan_takeover_delay_seconds)
                            )
                        )
                    )
                )
                if fallback:
                    resolved = self._resolve_remote_finish_payload(
                        event=fallback,
                        collected_segments=collected_segments,
                    )
                    if resolved:
                        return resolved, total_listen_ms, None
                    if collected_segments:
                        return " ".join(collected_segments).strip(), total_listen_ms, None

            self.sig_set_listening.emit(self.persona)
            timeout_seconds = (
                self._listen_timeout_seconds
                if not collected_segments
                else (
                    self._opponent_end_confirm_timeout_seconds
                    if awaiting_end_confirmation
                    else self._opponent_followup_timeout_seconds
                )
            )
            if self._lan_enabled and not collected_segments:
                timeout_seconds = min(timeout_seconds, self._lan_poll_timeout_seconds)
            started = time.monotonic()
            heard = ears.listen_for_turn(timeout_seconds=timeout_seconds)
            listen_ms = (time.monotonic() - started) * 1000.0
            total_listen_ms += listen_ms
            heard = " ".join((heard or "").split())

            if heard:
                awaiting_end_confirmation = False
                if self._looks_like_moderator_cue(heard):
                    cue = self._cue_from_text(heard, source="audio", listen_ms=listen_ms)
                    self._last_cue_ts = cue.ts
                    self._publish_moderator_cue(cue)
                    self.sig_ticker.emit("INTERRUPT: new moderator cue received (audio).")
                    return "", listen_ms, cue

                if not collected_segments or heard != collected_segments[-1]:
                    collected_segments.append(heard)
                if first_speech_ts is None:
                    first_speech_ts = time.time()
                floor_notice_sent = False
                if len(collected_segments) == 1:
                    self.sig_ticker.emit(
                        f"OPPONENT {self.remote_persona.upper()} speaking... waiting for full turn handoff."
                    )
                continue

            # If we already captured speech and then hit a no-speech window,
            # request one extra confirmation window before handoff.
            if collected_segments:
                if not awaiting_end_confirmation:
                    awaiting_end_confirmation = True
                    self.sig_ticker.emit("Opponent pause detected; confirming handoff...")
                    continue
                if first_speech_ts is not None and self._min_opponent_turn_seconds > 0:
                    elapsed = time.time() - first_speech_ts
                    if elapsed < self._min_opponent_turn_seconds:
                        if not floor_notice_sent:
                            remaining = self._min_opponent_turn_seconds - elapsed
                            self.sig_ticker.emit(
                                f"Holding handoff floor for opponent turn ({remaining:.1f}s remaining)..."
                            )
                            floor_notice_sent = True
                        continue

                if self._lan_enabled and self._opponent_finish_event_wait_seconds > 0:
                    final_event = self._wait_for_remote_finish_event(
                        expected_round_id=expected_round_id,
                        round_started_at=round_started_at,
                        allow_round_mismatch_if_audio=bool(collected_segments),
                        wait_seconds=self._opponent_finish_event_wait_seconds,
                    )
                    if final_event:
                        resolved = self._resolve_remote_finish_payload(
                            event=final_event,
                            collected_segments=collected_segments,
                        )
                        if resolved:
                            self.sig_ticker.emit("SYNC: finalized handoff from LAN completion event.")
                            return resolved, total_listen_ms, None
                return " ".join(collected_segments).strip(), total_listen_ms, None

        return "", 0.0, None

    def _speak_local_turn(
        self,
        prompt: str,
        round_id: str,
        round_started_at: float,
        listen_ms: float,
    ) -> LocalTurnOutcome:
        if not self._running:
            return LocalTurnOutcome("", 0.0, 0.0, interrupted=True)

        if not self.orchestrator.turn_available(self.persona):
            self.sig_ticker.emit(
                f"TURN LIMIT: {self.persona.upper()} already reached {self._max_turns_per_persona} turns; skipping."
            )
            return LocalTurnOutcome("", 0.0, 0.0, interrupted=False)

        cue = self._take_interrupt_cue(round_started_at)
        if cue is not None:
            return LocalTurnOutcome("", 0.0, 0.0, interrupted=True, interrupt_cue=cue)

        self.sig_set_thinking.emit(self.persona)
        self.sig_ticker.emit(f"PROMPT -> {self.persona.upper()}: {prompt}")

        reply, generate_ms = self._generate_response_with_retry(prompt)
        reply = self._format_turn_text(
            reply,
            target_words=(self._turn_min_words + self._turn_max_words) // 2,
            min_words=self._turn_min_words,
            max_words=self._turn_max_words,
            hard_cap=self._turn_hard_cap,
        )
        if not self._running:
            return LocalTurnOutcome("", generate_ms, 0.0, interrupted=True)
        if not reply:
            self.sig_ticker.emit(f"LLM returned empty response for {self.persona.upper()}; skipping turn.")
            return LocalTurnOutcome("", generate_ms, 0.0, interrupted=False)

        words = len(reply.split())
        if self.runtime.ears is not None:
            self.runtime.ears.mute_for(words / self._speech_words_per_second + 1.2)

        chunks = self._split_for_speech(reply)
        self.sig_start_speaking.emit(self.persona, reply)
        speak_started = time.monotonic()

        for chunk in chunks:
            cue = self._take_interrupt_cue(round_started_at)
            if cue is not None:
                if self.runtime.speaker is not None:
                    self.runtime.speaker.stop()
                self.sig_stop_speaking.emit(self.persona)
                self.sig_ticker.emit("INTERRUPT: local turn interrupted by new moderator cue.")
                return LocalTurnOutcome("", generate_ms, (time.monotonic() - speak_started) * 1000.0, True, cue)

            try:
                if self.runtime.speaker is not None:
                    self.runtime.speaker.speak(chunk)
            except Exception:
                logger.exception("Primary speaker failure for %s", self.persona)
                self.sig_ticker.emit(f"Voice output error on {self.persona.upper()} channel.")
                break

        speak_ms = (time.monotonic() - speak_started) * 1000.0
        self.sig_stop_speaking.emit(self.persona)

        self.orchestrator.record_candidate_turn(self.persona)
        self._remember_recent_turn(reply)
        turns = self.orchestrator.turns_spoken
        self.sig_ticker.emit(f"TURN COUNT | TRUMP={turns['trump']} | BIDEN={turns['biden']}")

        self.checker.check_async(reply, self.persona, self._on_fact_check_result)
        self._publish_local_turn(round_id=round_id, text=reply)

        metric = self.metrics.record_turn(
            persona=self.persona,
            round_index=turns[self.persona],
            words=words,
            listen_ms=listen_ms,
            generate_ms=generate_ms,
            speak_ms=speak_ms,
        )
        logger.info(
            "turn_complete persona=%s round=%s words=%s listen_ms=%.0f generate_ms=%.0f speak_ms=%.0f total_ms=%.0f",
            metric.persona,
            metric.round_index,
            metric.words,
            metric.listen_ms,
            metric.generate_ms,
            metric.speak_ms,
            metric.total_ms,
        )
        self.sig_ticker.emit(self.metrics.recent_summary())

        return LocalTurnOutcome(reply, generate_ms, speak_ms, interrupted=False)

    def _record_remote_turn(self, opponent_text: str, listen_ms: float) -> None:
        if not opponent_text.strip():
            return
        self._remember_recent_turn(opponent_text)
        self.orchestrator.record_candidate_turn(self.remote_persona)
        turns = self.orchestrator.turns_spoken
        self.sig_ticker.emit(f"OPPONENT ({self.remote_persona.upper()}): {opponent_text}")
        self.sig_ticker.emit(f"TURN COUNT | TRUMP={turns['trump']} | BIDEN={turns['biden']}")

        self.metrics.record_turn(
            persona=self.remote_persona,
            round_index=turns[self.remote_persona],
            words=len(opponent_text.split()),
            listen_ms=listen_ms,
            generate_ms=0.0,
            speak_ms=0.0,
        )
        self.sig_ticker.emit(self.metrics.recent_summary())

    def _generate_response_with_retry(self, prompt: str, attempts: int = 2) -> tuple[str, float]:
        brain = self.runtime.brain
        if brain is None:
            return "", 0.0

        for attempt in range(1, attempts + 1):
            if not self._running:
                return "", 0.0

            started = time.monotonic()
            try:
                reply = brain.generate_response(prompt)
                elapsed_ms = (time.monotonic() - started) * 1000.0
                return reply, elapsed_ms
            except Exception as exc:
                logger.warning(
                    "LLM generation failed persona=%s attempt=%s/%s err=%s",
                    self.persona,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    time.sleep(0.25 * attempt)

        fallback = getattr(brain, "_fallback_response", lambda: "I need a moment.")
        return fallback(), 0.0

    def _build_second_turn_prompt(self, moderator_prompt: str, opponent_text: str) -> str:
        if not opponent_text.strip():
            return f"Moderator question: {moderator_prompt}\n\nGive your direct answer in debate format."

        opponent_name = "Biden" if self.remote_persona == "biden" else "Trump"
        return (
            f"Moderator question: {moderator_prompt}\n\n"
            f"Opponent ({opponent_name}) said: {opponent_text}\n\n"
            "Respond directly to the moderator question, stay strictly on that topic, and rebut the opponent's main claim. "
            "Do not praise or endorse the opponent."
        )

    @staticmethod
    def _split_for_speech(text: str, max_chars: int = 220) -> list[str]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            return [text]

        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current = candidate

        if current:
            chunks.append(current)
        return chunks if chunks else [text]

    def _remember_recent_turn(self, text: str) -> None:
        clean = " ".join((text or "").split())
        if not clean:
            return
        self._recent_turn_texts.append(clean)
        if len(self._recent_turn_texts) > 6:
            self._recent_turn_texts = self._recent_turn_texts[-6:]

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        lowered = " ".join((text or "").lower().split())
        return re.sub(r"[^a-z0-9\s]", "", lowered).strip()

    def _is_recent_turn_echo(self, heard: str) -> bool:
        heard_norm = self._normalize_for_match(heard)
        if len(heard_norm.split()) < 3:
            return False

        for recent in reversed(self._recent_turn_texts):
            recent_norm = self._normalize_for_match(recent)
            if not recent_norm:
                continue
            if heard_norm == recent_norm:
                return True
            if len(heard_norm.split()) >= 4 and (heard_norm in recent_norm or recent_norm in heard_norm):
                return True
        return False

    @staticmethod
    def _contains_candidate_reference(text: str) -> bool:
        return bool(
            re.search(
                r"\b(trump|donald|biden|joe|mr\.?\s+(donald\s+)?trump|mr\.?\s+(joe\s+)?biden|president\s+(donald\s+)?trump|president\s+(joe\s+)?biden)\b",
                text or "",
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _strip_leading_fillers(text: str) -> str:
        sample = " ".join((text or "").lower().split())
        if not sample:
            return sample
        return re.sub(
            r"^(ok|okay|well|so|now|alright|all right|uh|um|ah|hmm)[,\s:;-]+",
            "",
            sample,
            flags=re.IGNORECASE,
        ).strip()

    @staticmethod
    def _looks_like_moderator_prompt(text: str) -> bool:
        sample = DebateWorker._strip_leading_fillers(text)
        if not sample:
            return False

        if DebateWorker._looks_like_moderator_cue(sample):
            return True

        if re.search(
            r"\b(first|start|starts|begin|begins)\s+(with\s+)?((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|biden|donald|joe)\b",
            sample,
            flags=re.IGNORECASE,
        ) or re.search(
            r"\b((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|biden|donald|joe)\s+(goes\s+)?(first|start|starts|begin|begins)\b",
            sample,
            flags=re.IGNORECASE,
        ):
            return True

        if re.search(
            r"\b(mr\.?\s+(donald\s+)?trump|mr\.?\s+(joe\s+)?biden|president\s+(donald\s+)?trump|president\s+(joe\s+)?biden)\b",
            sample,
            flags=re.IGNORECASE,
        ):
            return True

        if sample.startswith(("welcome", "welcome to", "good evening", "tonight")) and "debate" in sample:
            return True

        topical_starters = (
            "lets ",
            "let's ",
            "move on",
            "move to",
            "moving on",
            "new topic",
            "next topic",
            "question for",
            "i want to ask",
            "talk about",
            "on the topic of",
        )
        if any(sample.startswith(prefix) for prefix in topical_starters):
            return True

        words = sample.split()
        # Allow short moderator-style topic directives (e.g., "security and economy first")
        # while still requiring topic signals to reduce accidental triggers.
        if 2 <= len(words) <= 12:
            topic_words = (
                "economy",
                "inflation",
                "jobs",
                "tax",
                "trade",
                "immigration",
                "border",
                "healthcare",
                "crime",
                "security",
                "foreign",
                "ukraine",
                "russia",
                "china",
                "nato",
                "education",
                "climate",
                "energy",
            )
            directive_words = (
                "first",
                "next",
                "topic",
                "question",
                "discuss",
                "talk",
                "address",
                "focus",
            )
            topic_hits = sum(1 for token in topic_words if token in sample)
            has_directive = any(token in sample for token in directive_words)
            if (has_directive and topic_hits >= 1) or topic_hits >= 2:
                return True

        if "?" in sample and len(words) <= 45:
            if DebateWorker._contains_candidate_reference(sample):
                return True
            if re.search(r"\b(you|your)\b", sample):
                return True
        return False

    @staticmethod
    def _looks_like_moderator_cue(text: str) -> bool:
        sample = DebateWorker._strip_leading_fillers(text)
        if not sample:
            return False

        words = sample.split()
        if not words:
            return False
        if len(words) == 1:
            return words[0] in {"trump", "donald", "biden", "joe", "next"}

        if sample.startswith(("next question", "new question", "next topic", "move on", "moving on", "let's move")):
            return True

        if re.search(
            r"\b(first|start|starts|begin|begins)\s+(with\s+)?((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|biden|donald|joe)\b",
            sample,
            flags=re.IGNORECASE,
        ) or re.search(
            r"\b((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|biden|donald|joe)\s+(goes\s+)?(first|start|starts|begin|begins)\b",
            sample,
            flags=re.IGNORECASE,
        ):
            return True

        if re.match(
            r"^(hey\s+)?((mr|president)\.?\s+)?(trump|biden|donald|joe)\b",
            sample,
            flags=re.IGNORECASE,
        ):
            return True

        question_starters = (
            "what ",
            "why ",
            "how ",
            "when ",
            "where ",
            "who ",
            "is ",
            "will ",
            "would ",
            "should ",
            "are we",
            "do we",
            "can we",
        )
        starts_like_question = any(sample.startswith(prefix) for prefix in question_starters)
        if starts_like_question:
            explicit_address = DebateWorker._contains_candidate_reference(sample)
            second_person = bool(re.search(r"\b(you|your)\b", sample))
            collective_question = sample.startswith(("are we", "do we", "can we"))

            if "?" in sample and len(words) <= 24 and (explicit_address or second_person or collective_question):
                return True
            if len(words) <= 16 and (explicit_address or second_person or collective_question):
                return True

        if "?" in sample and len(words) <= 40 and re.search(r"\b(you|your)\b", sample):
            return True

        return False

    @staticmethod
    def _looks_like_opponent_opening(text: str) -> bool:
        sample = " ".join((text or "").lower().split())
        if not sample:
            return False

        words = re.findall(r"[a-z0-9']+", sample)
        if len(words) < 3:
            return False

        if DebateWorker._looks_like_moderator_prompt(sample):
            return False

        if sample.endswith("?"):
            return False

        if re.search(r"\b(i|we|my|our)\b", sample):
            return True

        if re.search(r"\b(look[, ]+folks|here'?s the deal|let me tell you|c['’]?mon man|everybody knows it)\b", sample):
            return True

        if len(words) < 6:
            return False

        policy_terms = (
            "economy",
            "inflation",
            "jobs",
            "tax",
            "trade",
            "immigration",
            "border",
            "healthcare",
            "security",
            "iran",
            "ukraine",
            "nato",
            "china",
        )
        topic_hits = sum(1 for token in policy_terms if token in sample)
        return topic_hits >= 2

    def _is_startup_short_topic_cue(self, text: str) -> bool:
        # Allow one-word moderator topic kickoffs only before first recorded turn.
        # This avoids regressing into "always-listening" when user says just "Economy."
        if self._recent_turn_texts:
            return False
        words = re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(words) != 1:
            return False
        return words[0] in {
            "economy",
            "inflation",
            "jobs",
            "taxes",
            "trade",
            "immigration",
            "border",
            "healthcare",
            "security",
            "climate",
            "energy",
            "education",
            "ukraine",
            "russia",
            "china",
            "iran",
            "trump",
            "biden",
            "donald",
            "joe",
        }

    @staticmethod
    def _is_transition_only_prompt(text: str) -> bool:
        sample = DebateWorker._strip_leading_fillers(text)
        if not sample:
            return False
        if "?" in sample:
            return False
        if DebateWorker._contains_candidate_reference(sample):
            return False

        words = sample.split()
        if len(words) > 14:
            return False

        transition_patterns = (
            r"\bmove on\b",
            r"\bmoving on\b",
            r"\bmove to\b",
            r"\bnext topic\b",
            r"\bnew topic\b",
            r"\bnext question\b",
            r"\blet'?s move\b",
            r"\bon to the next\b",
        )
        return any(re.search(pattern, sample, flags=re.IGNORECASE) for pattern in transition_patterns)

    def _coalesce_moderator_prompt(self, prompt: str, ears) -> tuple[str, float]:
        if not self._cue_coalesce_enabled or ears is None:
            return prompt, 0.0

        merged = " ".join((prompt or "").split())
        if not merged:
            return merged, 0.0

        added_ms = 0.0
        segments_used = 0

        while segments_used < self._cue_coalesce_max_segments and self._looks_like_partial_moderator_prompt(merged):
            self.sig_ticker.emit("Moderator cue seems partial; waiting for continuation...")
            started = time.monotonic()
            continuation = ears.listen_for_turn(timeout_seconds=self._cue_coalesce_window_seconds)
            added_ms += (time.monotonic() - started) * 1000.0
            continuation = " ".join((continuation or "").split())
            if not continuation:
                break

            if self._is_recent_turn_echo(continuation):
                segments_used += 1
                self.sig_ticker.emit("Ignored echo while extending moderator cue.")
                continue

            # If the next segment sounds like a candidate response, do not append it.
            if self._looks_like_opponent_opening(continuation) and not self._looks_like_moderator_prompt(continuation):
                self._prefetched_opponent_segment = continuation
                self.sig_ticker.emit("Stopped cue extension; continuation sounded like candidate speech.")
                break

            merged = f"{merged} {continuation}".strip()
            segments_used += 1

        return merged, added_ms

    def _looks_like_partial_moderator_prompt(self, text: str) -> bool:
        sample = self._strip_leading_fillers(text)
        if not sample:
            return False

        words = re.findall(r"[a-z0-9']+", sample)
        if not words:
            return False
        if len(words) <= 2:
            return True

        if self._is_transition_only_prompt(sample):
            return True

        if self._contains_candidate_reference(sample) and "?" not in sample and len(words) <= 6:
            return True

        if sample.endswith("?"):
            if len(words) <= 7:
                topic_terms = (
                    "economy",
                    "inflation",
                    "jobs",
                    "tax",
                    "trade",
                    "immigration",
                    "border",
                    "healthcare",
                    "security",
                    "iran",
                    "ukraine",
                    "nato",
                    "china",
                    "greenland",
                )
                if not any(token in sample for token in topic_terms):
                    return True

        trailing_tokens = {
            "if",
            "when",
            "as",
            "to",
            "for",
            "with",
            "and",
            "or",
            "that",
            "about",
            "regarding",
            "on",
            "in",
            "at",
            "of",
            "are",
            "is",
            "will",
            "would",
            "should",
            "could",
            "do",
            "did",
        }
        if len(words) <= 16 and words[-1] in trailing_tokens:
            return True

        return False

    def _cue_from_text(self, text: str, source: str, listen_ms: float = 0.0) -> ModeratorCue:
        cleaned = " ".join((text or "").split())
        ts = time.time()
        first = DebateOrchestrator.choose_first_speaker(cleaned)
        seed = f"{cleaned.lower()}|{first}|{int(ts * 2)}"
        round_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return ModeratorCue(
            prompt=cleaned,
            first_speaker=first,
            round_id=round_id,
            source=source,
            ts=ts,
            listen_ms=listen_ms,
        )

    @staticmethod
    def _cue_from_event(event: dict, source: str) -> ModeratorCue:
        prompt = " ".join(str(event.get("prompt", "")).split())
        first = str(event.get("first_speaker", DebateOrchestrator.choose_first_speaker(prompt))).lower()
        if first not in {"trump", "biden"}:
            first = DebateOrchestrator.choose_first_speaker(prompt)
        round_id = str(event.get("round_id", "")) or hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
        return ModeratorCue(
            prompt=prompt,
            first_speaker=first,
            round_id=round_id,
            source=source,
            ts=DebateWorker._event_ts(event),
            listen_ms=0.0,
        )

    def _publish_moderator_cue(self, cue: ModeratorCue) -> None:
        if not self._lan_enabled or self.lan is None:
            return
        self.lan.publish(
            "moderator_cue",
            prompt=cue.prompt,
            first_speaker=cue.first_speaker,
            round_id=cue.round_id,
            persona="moderator",
        )

    def _publish_local_turn(self, round_id: str, text: str) -> None:
        if not self._lan_enabled or self.lan is None:
            return
        self.lan.publish(
            "speaker_finished",
            persona=self.persona,
            round_id=round_id,
            text=text,
        )

    def _wait_for_remote_finish_event(
        self,
        expected_round_id: str,
        round_started_at: float,
        allow_round_mismatch_if_audio: bool,
        wait_seconds: float,
    ) -> dict | None:
        if not self._lan_enabled:
            return None
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while self._running:
            event = self._take_lan_event(
                lambda e: (
                    e.get("type") == "speaker_finished"
                    and e.get("persona") == self.remote_persona
                    and self._event_ts(e) >= (round_started_at - 0.1)
                    and (
                        str(e.get("round_id", "")).strip() == expected_round_id
                        or allow_round_mismatch_if_audio
                    )
                )
            )
            if event:
                return event
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.03)
        return None

    def _resolve_remote_finish_payload(self, event: dict, collected_segments: list[str]) -> str:
        payload_text = " ".join(str(event.get("text", "")).split())
        if payload_text:
            if collected_segments:
                local_audio_text = " ".join(collected_segments).strip()
                if len(payload_text.split()) >= len(local_audio_text.split()):
                    self.sig_ticker.emit("SYNC FALLBACK: using LAN opponent turn payload.")
                    return payload_text
                merged = " ".join([local_audio_text, payload_text]).strip()
                self.sig_ticker.emit("SYNC FALLBACK: merging audio+LAN opponent payload.")
                return merged
            self.sig_ticker.emit("SYNC FALLBACK: using LAN opponent turn payload.")
            return payload_text
        return ""

    def _sleep_until_second_speaker(self, round_started_at: float) -> ModeratorCue | None:
        delay = max(0.0, self._second_speaker_start_delay_seconds)
        if delay <= 0:
            return None

        deadline = time.monotonic() + delay
        while self._running and time.monotonic() < deadline:
            cue = self._take_interrupt_cue(round_started_at)
            if cue is not None:
                return cue
            time.sleep(0.04)
        return None

    def _harmonize_audio_cue(self, audio_cue: ModeratorCue) -> ModeratorCue:
        """Audio stays primary, but accept a more specific LAN cue for this same moment."""
        if not self._lan_enabled:
            return audio_cue
        deadline = time.monotonic() + self._cue_sync_grace_seconds
        selected = audio_cue

        while self._running and time.monotonic() < deadline:
            event = self._take_lan_event(
                lambda e: (
                    e.get("type") == "moderator_cue"
                    and abs(self._event_ts(e) - audio_cue.ts) <= 2.5
                )
            )
            if not event:
                time.sleep(0.03)
                continue

            lan_cue = self._cue_from_event(event, source="lan")
            selected = self._select_preferred_cue(audio_cue, lan_cue)
            if selected.source == "lan" and selected.first_speaker != audio_cue.first_speaker:
                self.sig_ticker.emit("SYNC: adopted LAN cue routing for this round.")
            break

        return selected

    @staticmethod
    def _select_preferred_cue(audio_cue: ModeratorCue, lan_cue: ModeratorCue) -> ModeratorCue:
        audio_score = DebateWorker._cue_specificity_score(audio_cue.prompt)
        lan_score = DebateWorker._cue_specificity_score(lan_cue.prompt)
        if lan_score > audio_score:
            return lan_cue
        if audio_score > lan_score:
            return audio_cue
        if audio_cue.first_speaker == lan_cue.first_speaker:
            return audio_cue
        # Deterministic tie break (same result on both laptops) to avoid split-brain.
        audio_norm = " ".join(re.findall(r"[a-z0-9]+", (audio_cue.prompt or "").lower()))
        lan_norm = " ".join(re.findall(r"[a-z0-9]+", (lan_cue.prompt or "").lower()))
        if len(lan_norm) > len(audio_norm):
            return lan_cue
        if len(audio_norm) > len(lan_norm):
            return audio_cue
        if lan_norm < audio_norm:
            return lan_cue
        if audio_norm < lan_norm:
            return audio_cue
        # Final deterministic fallback: default starter is Trump.
        return audio_cue if audio_cue.first_speaker == "trump" else lan_cue

    @staticmethod
    def _cue_specificity_score(text: str) -> int:
        sample = " ".join((text or "").lower().split())
        if not sample:
            return 0

        strong_patterns = (
            r"\b(first|start|starts|begin|begins)\s+(with\s+)?((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|donald|biden|joe)\b",
            r"\b((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|donald|biden|joe)\s+(goes\s+)?(first|start|starts|begin|begins)\b",
            r"^(hey\s+)?((mr|president)\.?\s+)?((donald|joe)\s+)?(trump|donald|biden|joe)\b",
        )
        if any(re.search(pattern, sample, flags=re.IGNORECASE) for pattern in strong_patterns):
            return 2

        if re.search(r"\b(trump|donald|biden|joe)\b", sample, flags=re.IGNORECASE):
            return 1

        return 0

    @staticmethod
    def _event_ts(event: dict) -> float:
        try:
            return float(event.get("_recv_ts", event.get("ts", time.time())))
        except Exception:
            return time.time()

    def _is_duplicate_active_round_cue(self, cue: ModeratorCue) -> bool:
        active_prompt = " ".join((self._active_round_prompt or "").split())
        if not active_prompt:
            return False
        if cue.first_speaker != self._active_round_first_speaker:
            return False

        overlap = self._token_overlap_ratio(active_prompt, cue.prompt)
        return overlap >= 0.72

    @staticmethod
    def _token_overlap_ratio(a: str, b: str) -> float:
        a_tokens = set(re.findall(r"[a-z0-9]+", (a or "").lower()))
        b_tokens = set(re.findall(r"[a-z0-9]+", (b or "").lower()))
        if not a_tokens or not b_tokens:
            return 0.0
        shared = len(a_tokens & b_tokens)
        return shared / float(max(1, min(len(a_tokens), len(b_tokens))))

    def _emit_sync_status(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_sync_status_emit_at) < self._sync_status_emit_interval_seconds:
            return

        if not self._lan_enabled:
            state, detail = "disabled", "LAN FAILSAFE OFF"
        elif self.lan is None:
            state, detail = "error", "LAN FAILSAFE UNAVAILABLE"
        else:
            snapshot = self.lan.connection_snapshot(timeout_seconds=self._lan_peer_timeout_seconds)
            peers = int(snapshot.get("recent_peer_count", 0))
            if peers > 0:
                state = "connected"
                detail = f"LAN FAILSAFE CONNECTED ({peers} peer{'s' if peers != 1 else ''})"
            else:
                state = "searching"
                detail = "LAN FAILSAFE SEARCHING"

        key = f"{state}|{detail}"
        if force or key != self._last_sync_status_key:
            self.sig_sync_status.emit(state, detail)
            self._last_sync_status_key = key
        self._last_sync_status_emit_at = now

    def _refresh_lan_backlog(self) -> None:
        if not self._lan_enabled or self.lan is None:
            return
        events = self.lan.drain_events()
        if events:
            relevant = [
                event
                for event in events
                if event.get("type") in {"moderator_cue", "speaker_finished"}
            ]
            if relevant:
                self._lan_backlog.extend(relevant)

    def _take_lan_event(self, predicate) -> dict | None:
        if not self._lan_enabled:
            return None
        self._refresh_lan_backlog()
        for idx, event in enumerate(self._lan_backlog):
            try:
                if predicate(event):
                    return self._lan_backlog.pop(idx)
            except Exception:
                continue
        return None

    def _take_interrupt_cue(self, round_started_at: float) -> ModeratorCue | None:
        if not self._lan_enabled:
            return None
        while True:
            event = self._take_lan_event(
                lambda e: (
                    e.get("type") == "moderator_cue"
                    and self._event_ts(e) > max(self._last_cue_ts, round_started_at)
                    and (time.time() - round_started_at) >= self._interrupt_min_delay_seconds
                )
            )
            if not event:
                return None

            cue = self._cue_from_event(event, source="lan")
            if self._is_duplicate_active_round_cue(cue):
                self._last_cue_ts = max(self._last_cue_ts, cue.ts)
                logger.info("Ignoring duplicate moderator cue during active round: %s", cue.prompt[:120])
                continue

            self._last_cue_ts = cue.ts
            return cue

    def _on_fact_check_result(self, result: dict) -> None:
        if not self._running:
            return

        verdict = result.get("verdict", "UNVERIFIABLE")
        claim = result.get("claim", "")
        real_stat = result.get("real_stat", "")

        self.sig_fact_check.emit(verdict, claim, real_stat)
        self.sig_ticker.emit(f"FACT CHECK [{verdict}]: {claim[:80]}...")

    @staticmethod
    def _format_turn_text(
        text: str,
        target_words: int = 50,
        min_words: int = 40,
        max_words: int = 55,
        hard_cap: int = 70,
    ) -> str:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return ""

        words = cleaned.split()
        if len(words) <= max_words:
            return cleaned

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
                if count >= min_words:
                    break
                if count + wc <= hard_cap:
                    selected.append(sentence)
                    count += wc
                break

            if selected:
                merged = " ".join(selected).strip()
                merged_words = len(merged.split())
                if min_words <= merged_words <= hard_cap:
                    return merged

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

        clipped = " ".join(words[:max_words]).rstrip(" ,;:")
        if clipped and clipped[-1] not in ".!?":
            clipped += "."
        return clipped

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self.orchestrator.stop()
        self._cleanup_once()

    def reset(self) -> None:
        if self.runtime.brain is not None:
            self.runtime.brain.reset()
        self.orchestrator.reset()
        self.sig_ticker.emit("DEBATE RESET - local candidate memory and state reset.")

    def _cleanup_once(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True

        if self._lan_enabled and self.lan is not None:
            try:
                self.lan.stop()
            except Exception:
                pass

        try:
            self.runtime.close()
        except Exception:
            logger.exception("Runtime cleanup failure")


class DebateApp:
    """Wire selector, dashboard, and background worker."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.worker: DebateWorker | None = None
        self.gui: DebateDashboard | None = None
        self.selector: DebateModeSelector | None = None

        self.app.aboutToQuit.connect(self._on_app_quit)
        self._show_mode_selector()

    def _show_mode_selector(self) -> None:
        if self.selector is not None:
            self.selector.close()

        self.selector = DebateModeSelector()
        self.selector.mode_selected.connect(self._on_mode_selected)
        self.selector.show()

    def _on_mode_selected(self, persona: str, brain_mode: str, voice_mode: str) -> None:
        mod_label = module_label(brain_mode, voice_mode)

        logger.info(
            "Mode selection persona=%s brain=%s voice=%s",
            persona,
            brain_mode,
            voice_mode,
        )

        if self.selector is not None:
            self.selector.close()

        self.gui = DebateDashboard(local_persona=persona, module_label=mod_label)
        self.gui.sig_back_requested.connect(self._return_to_mode_selector)
        self.gui.keyPressEvent = self._on_key_press
        self.gui.show()

        try:
            self.worker = DebateWorker(
                persona=persona,
                voice_mode=voice_mode,
                brain_type=brain_mode,
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
        self.worker.sig_sync_status.connect(self.gui.set_sync_status)
        self.worker.start()

    def _stop_worker(self) -> None:
        if self.worker is None:
            return

        self.worker.stop()
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
        if key == Qt.Key.Key_F:
            enabled = self.worker.checker.toggle()
            if self.gui is not None:
                self.gui.add_ticker_message(f"FACT CHECKER: {'ON' if enabled else 'OFF'}")
        elif key == Qt.Key.Key_C:
            self.worker.sfx.play("applause", volume=0.6)
        elif key == Qt.Key.Key_R:
            self.worker.reset()
        elif key == Qt.Key.Key_Escape:
            self._stop_worker()
            self.app.quit()

    def _on_app_quit(self) -> None:
        self._stop_worker()

    def run(self) -> None:
        sys.exit(self.app.exec())


def main() -> int:
    setup_logging()

    app = DebateApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
