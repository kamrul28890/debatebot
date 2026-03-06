"""Runtime service bootstrap for dual-laptop live debates."""

from __future__ import annotations

from dataclasses import dataclass

from src.audio.listener import DebateListener
from src.audio.sound_effects import SoundEffectsEngine
from src.audio.xtts_speaker import DualSpeaker
from src.brain.fact_checker import FactChecker
from src.brain.model import DebateBrain


@dataclass(frozen=True)
class RuntimeBootstrapResult:
    active_brain_label: str
    startup_messages: list[str]


class NullFactChecker:
    """No-op checker when Azure fact-check credentials are unavailable."""

    def __init__(self) -> None:
        self.enabled = False

    def check_async(self, statement: str, speaker: str, callback) -> None:
        return

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled


class DebateRuntime:
    """Holds heavy runtime services initialized in worker thread."""

    def __init__(self) -> None:
        self.local_persona: str = "trump"
        self.remote_persona: str = "biden"
        self.brain: DebateBrain | None = None
        self.speaker: DualSpeaker | None = None
        self.ears: DebateListener | None = None
        self.sfx: SoundEffectsEngine | None = None
        self.checker: FactChecker | NullFactChecker | None = None

    @staticmethod
    def other_persona(persona: str) -> str:
        return "biden" if persona == "trump" else "trump"

    def bootstrap(
        self,
        local_persona: str,
        brain_type: str,
        voice_mode: str,
    ) -> RuntimeBootstrapResult:
        startup_messages: list[str] = []

        self.local_persona = local_persona if local_persona in {"trump", "biden"} else "trump"
        self.remote_persona = self.other_persona(self.local_persona)

        self.brain = DebateBrain(self.local_persona, brain_type=brain_type)
        self.speaker = DualSpeaker(self.local_persona, mode=voice_mode)

        active_brain = self.brain.brain_type
        if brain_type == "qwen" and self.brain.brain_type != "qwen":
            startup_messages.append(
                f"Qwen fallback active for {self.local_persona.upper()}: {self.brain.qwen_init_error}"
            )

        if voice_mode == "xtts" and self.speaker.mode != "xtts":
            startup_messages.append(
                f"Voice fallback active for {self.local_persona.upper()}: XTTS unavailable; using Azure TTS."
            )

        # Slightly longer silence windows reduce premature end-of-turn detection.
        self.ears = DebateListener(silence_timeout_ms=1800, initial_silence_timeout_ms=3200)
        self.sfx = SoundEffectsEngine()

        try:
            self.checker = FactChecker()
        except Exception as exc:
            self.checker = NullFactChecker()
            startup_messages.append(
                "Fact checker unavailable (missing Azure OpenAI credentials); continuing without checks."
            )
            startup_messages.append(f"Fact-check init reason: {exc}")

        return RuntimeBootstrapResult(
            active_brain_label=active_brain,
            startup_messages=startup_messages,
        )

    def close(self) -> None:
        if self.checker is not None:
            try:
                self.checker.enabled = False
            except Exception:
                pass

        if self.ears is not None:
            try:
                self.ears.stop()
            except Exception:
                pass

        if self.speaker is not None:
            try:
                self.speaker.stop()
            except Exception:
                pass

        if self.brain is not None:
            try:
                if self.brain.brain_type == "qwen" and hasattr(self.brain, "qwen_brain"):
                    self.brain.qwen_brain.unload_model()
            except Exception:
                pass
