"""
src/audio/sound_effects.py

Crowd reaction sound effects engine (applause-only).
"""

from __future__ import annotations

import logging
import os
import threading


logger = logging.getLogger(__name__)


try:
    import pygame

    _PYGAME_IMPORTED = True
except Exception as exc:
    _PYGAME_IMPORTED = False
    logger.warning("[SoundFX] pygame unavailable - sound effects disabled (%s)", exc)


class SoundEffectsEngine:
    """
    Applause-only sound effects.

    Background auto reactions are intentionally disabled to keep sessions quiet.
    Use `play('applause')` for explicit applause events.
    """

    SOUND_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "crowd_sounds",
    )

    SOUNDS = {
        "applause": "applause",
    }
    SUPPORTED_EXTENSIONS = (".wav", ".ogg", ".oga", ".mp3")

    def __init__(self):
        self._lock = threading.Lock()
        self._last_played: dict[str, float] = {}
        self._sounds: dict[str, object | None] = {}
        self.enabled = True
        self._audio_ready = self._init_audio()
        self._load_sounds()

    def react_to_speech(self, text: str, speaker: str = "") -> None:
        # Disabled by design: no automatic background reactions.
        return

    def play_fact_check_fail(self) -> None:
        # Disabled by request: applause-only profile.
        return

    def play_fact_check_pass(self) -> None:
        # Disabled by request: applause-only profile.
        return

    def play_opening_fanfare(self) -> None:
        # Disabled by request: applause-only profile.
        return

    def play(self, sound_name: str, volume: float = 0.7) -> None:
        if not self.enabled or not self._audio_ready:
            return
        if sound_name != "applause":
            return

        import time

        now = time.time()
        with self._lock:
            last = self._last_played.get(sound_name, 0.0)
            if now - last < 1.0:
                return
            self._last_played[sound_name] = now

        thread = threading.Thread(
            target=self._play_worker,
            args=(sound_name, volume),
            daemon=True,
        )
        thread.start()

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def _load_sounds(self) -> None:
        if not self._audio_ready:
            return

        for name, stem in self.SOUNDS.items():
            path = self._resolve_sound_file(stem)
            if path and os.path.exists(path):
                try:
                    self._sounds[name] = pygame.mixer.Sound(path)
                    logger.info("[SoundFX] Loaded sound: %s (%s)", name, os.path.basename(path))
                except Exception as exc:
                    self._sounds[name] = None
                    logger.warning("[SoundFX] Could not load %s (%s)", name, exc)
            else:
                self._sounds[name] = None
                expected = ", ".join(f"{stem}{ext}" for ext in self.SUPPORTED_EXTENSIONS)
                logger.warning("[SoundFX] Missing sound file for %s. Expected one of: %s", name, expected)

    def _resolve_sound_file(self, stem: str) -> str | None:
        for ext in self.SUPPORTED_EXTENSIONS:
            candidate = os.path.join(self.SOUND_DIR, f"{stem}{ext}")
            if os.path.exists(candidate):
                return candidate
        return None

    def _play_worker(self, sound_name: str, volume: float) -> None:
        if not self._audio_ready:
            return

        sound = self._sounds.get(sound_name)
        if sound is None:
            return

        try:
            sound.set_volume(volume)
            sound.play()
        except Exception as exc:
            logger.warning("[SoundFX] Error playing %s: %s", sound_name, exc)

    def _init_audio(self) -> bool:
        if not _PYGAME_IMPORTED:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            return True
        except Exception as exc:
            logger.warning("[SoundFX] pygame mixer init failed - disabling SFX (%s)", exc)
            return False
