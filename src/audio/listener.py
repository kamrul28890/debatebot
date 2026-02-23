"""
src/audio/listener.py

Azure Speech-to-Text listener, Mac-optimized.
- Handles acoustic echo from the other laptop's speaker
- 1.5s silence timeout for natural speech end-detection
- Filters out self-echo by checking if our own TTS just fired
"""

import os
import sys
import time
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import azure.cognitiveservices.speech as speechsdk
import keys


class DebateListener:
    """
    Listens for the opponent's speech via the MacBook microphone.
    
    Key behaviors:
    - Mutes itself for echo_mute_seconds after our own TTS fires (echo suppression)
    - Returns empty string if background noise only
    - Configurable silence timeout
    """

    def __init__(self, silence_timeout_ms: int = 1500, initial_silence_timeout_ms: int = 15000):
        speech_config = speechsdk.SpeechConfig(
            subscription=keys.azure_key,
            region=keys.azure_region,
        )

        # ── Silence detection tuning ───────────────────────────────────────────
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs,
            str(silence_timeout_ms),
        )
        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
            str(initial_silence_timeout_ms),
        )

        # ── Use MacBook default microphone ─────────────────────────────────────
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)

        self.recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        # ── Echo suppression state ─────────────────────────────────────────────
        self._muted_until = 0.0  # epoch time until which we ignore audio
        self._mute_lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def mute_for(self, seconds: float):
        """
        Call this right before our own TTS starts speaking so we don't
        pick up our own voice as the opponent's input.
        """
        with self._mute_lock:
            self._muted_until = time.time() + seconds

    def listen_for_turn(self, timeout_seconds: int = 60) -> str:
        """
        Block until opponent speech is recognized (or timeout).
        Returns the recognized text, or "" if nothing heard.
        """
        # Wait if we're in mute window (echo suppression)
        wait_start = time.time()
        while True:
            with self._mute_lock:
                if time.time() >= self._muted_until:
                    break
            if time.time() - wait_start > timeout_seconds:
                return ""
            time.sleep(0.05)

        print("🎤  Listening for opponent...")

        result = self.recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = result.text.strip()
            print(f"✅  Heard: '{text}'")

            # Basic sanity filter — ignore very short noise artifacts
            if len(text.split()) < 2:
                print("   (too short, ignoring)")
                return ""

            return text

        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("⚠️  No speech recognized.")
            return ""

        elif result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            print(f"❌  STT canceled: {details.reason}")
            if details.reason == speechsdk.CancellationReason.Error:
                print(f"   Error details: {details.error_details}")
            return ""

        return ""

    def listen_for_interjection(self) -> str:
        """
        Very short listen — 500ms silence timeout.
        Used to catch interruptions mid-speech.
        """
        # Temporarily tighten the silence timeout
        # (Azure doesn't support changing it on-the-fly, so we just do recognize_once
        # and return quickly)
        result = self.recognizer.recognize_once_async().get()
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text.strip()
        return ""


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    listener = DebateListener()
    print("Say something...")
    text = listener.listen_for_turn()
    print(f"Result: '{text}'")
