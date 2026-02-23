"""
src/audio/sound_effects.py

Crowd reaction sound effects engine.
- Applause, laughter, booing, fact-check buzzer, fanfare
- Triggered by keyword analysis of debate text
- Non-blocking (plays in background thread)
"""

import os
import sys
import re
import threading
import random

# pygame for cross-platform audio on Mac
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("[SoundFX] pygame not available — sound effects disabled")


# ── Trigger keywords ──────────────────────────────────────────────────────────
APPLAUSE_TRIGGERS = [
    "american people", "united states", "freedom", "democracy", "constitution",
    "veterans", "military", "god bless", "thank you", "together", "history",
]

LAUGH_TRIGGERS = [
    "believe me", "nobody knew", "the best", "tremendous", "malarkey",
    "no joke", "here's the deal", "c'mon man", "sleepy", "witch hunt",
    "perfect phone call", "covfefe",
]

BOO_TRIGGERS = [
    "fake news", "radical left", "open border", "crime", "disaster",
    "terrible", "worst ever", "failed", "corrupt", "lies",
]

# Siskind gets applause when he restores order
SISKIND_APPLAUSE = ["moving on", "gentlemen", "time is up", "next topic"]


class SoundEffectsEngine:
    """
    Analyzes debate text and triggers crowd reactions.
    All sounds play asynchronously.
    """

    # Paths to sound files (user must place these in data/crowd_sounds/)
    SOUND_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "crowd_sounds"
    )

    SOUNDS = {
        "applause":    "applause.wav",
        "laugh":       "laugh.wav",
        "boo":         "boo.wav",
        "buzzer":      "buzzer.wav",        # fact-check fail
        "ding":        "ding.wav",          # fact-check pass
        "fanfare":     "fanfare.wav",       # opening / winner
        "crickets":    "crickets.wav",      # awkward silence
        "drumroll":    "drumroll.wav",      # before a big claim
    }

    def __init__(self):
        self._channels = {}
        self._lock = threading.Lock()
        self._last_played = {}   # sound_name -> timestamp, to prevent spam
        self._load_sounds()
        self.enabled = True

    def react_to_speech(self, text: str, speaker: str = ""):
        """
        Analyze text and auto-trigger the most appropriate crowd reaction.
        Call this after a candidate finishes speaking.
        """
        if not self.enabled:
            return

        text_lower = text.lower()

        # Check boo first (attacks get boos)
        if any(kw in text_lower for kw in BOO_TRIGGERS):
            self.play("boo", volume=0.5)
            return

        # Laughter triggers
        if any(kw in text_lower for kw in LAUGH_TRIGGERS):
            self.play("laugh", volume=0.6)
            return

        # Applause triggers
        if any(kw in text_lower for kw in APPLAUSE_TRIGGERS):
            self.play("applause", volume=0.7)
            return

        # Siskind restoring order gets light applause
        if speaker == "siskind" and any(kw in text_lower for kw in SISKIND_APPLAUSE):
            self.play("applause", volume=0.3)
            return

        # Random ambient murmur (10% chance)
        if random.random() < 0.1:
            self.play("applause", volume=0.2)

    def play_fact_check_fail(self):
        """Buzzer + dramatic sting for when a lie is caught."""
        self.play("buzzer", volume=0.8)

    def play_fact_check_pass(self):
        """Light ding for verified true statement."""
        self.play("ding", volume=0.5)

    def play_opening_fanfare(self):
        """Fanfare at debate start."""
        self.play("fanfare", volume=0.9)

    def play(self, sound_name: str, volume: float = 0.7):
        """Play a sound asynchronously. Prevents spam (1s cooldown per sound)."""
        if not self.enabled or not PYGAME_AVAILABLE:
            return

        import time
        now = time.time()
        with self._lock:
            last = self._last_played.get(sound_name, 0)
            if now - last < 1.0:
                return  # cooldown
            self._last_played[sound_name] = now

        t = threading.Thread(target=self._play_worker, args=(sound_name, volume), daemon=True)
        t.start()

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_sounds(self):
        """Pre-load all sound files."""
        if not PYGAME_AVAILABLE:
            return
        self._sounds = {}
        for name, filename in self.SOUNDS.items():
            path = os.path.join(self.SOUND_DIR, filename)
            if os.path.exists(path):
                try:
                    self._sounds[name] = pygame.mixer.Sound(path)
                    print(f"   ✅ Loaded sound: {name}")
                except Exception as e:
                    print(f"   ⚠️ Could not load {name}: {e}")
            else:
                # Create a silent placeholder so we don't crash
                self._sounds[name] = None
                print(f"   ⚠️ Missing sound file: {path}")

    def _play_worker(self, sound_name: str, volume: float):
        if not PYGAME_AVAILABLE:
            return
        sound = self._sounds.get(sound_name)
        if sound is None:
            return
        try:
            sound.set_volume(volume)
            sound.play()
        except Exception as e:
            print(f"[SoundFX] Error playing {sound_name}: {e}")


# ── How to get sound files ─────────────────────────────────────────────────────
# Option 1: Download from freesound.org (free, CC licensed):
#   - Applause: https://freesound.org/search/?q=applause+crowd
#   - Laughter: https://freesound.org/search/?q=audience+laughter
#   - Boo:      https://freesound.org/search/?q=crowd+booing
#   - Buzzer:   https://freesound.org/search/?q=game+show+buzzer
#   - Ding:     https://freesound.org/search/?q=correct+ding
#
# Option 2: Use the download_sounds.py script in scripts/
# ─────────────────────────────────────────────────────────────────────────────


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time

    sfx = SoundEffectsEngine()

    print("Testing crowd reactions...")
    sfx.react_to_speech("We believe in freedom and the American people!", "trump")
    time.sleep(3)

    sfx.react_to_speech("Nobody knew healthcare could be so complicated. Believe me.", "trump")
    time.sleep(3)

    sfx.play_fact_check_fail()
    time.sleep(2)
    print("Done.")
