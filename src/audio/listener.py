"""
src/audio/listener.py

Azure Speech-to-Text listener, Mac-optimized.
- Handles acoustic echo from the other laptop's speaker
- 1.5s silence timeout for natural speech end-detection
- Filters out self-echo by checking if our own TTS just fired
"""

import logging
import os
import time
import threading

import azure.cognitiveservices.speech as speechsdk
from src.config import settings

logger = logging.getLogger(__name__)


class DebateListener:
    """
    Listens for the opponent's speech via the MacBook microphone.
    
    Key behaviors:
    - Mutes itself for echo_mute_seconds after our own TTS fires (echo suppression)
    - Returns empty string if background noise only
    - Configurable silence timeout
    """

    def __init__(self, silence_timeout_ms: int = 1500, initial_silence_timeout_ms: int = 8000):
        settings.require_speech()
        self._silence_timeout_ms = _env_int("DEBATE_STT_SEGMENTATION_SILENCE_MS", silence_timeout_ms)
        self._initial_silence_timeout_ms = _env_int("DEBATE_STT_INITIAL_SILENCE_MS", initial_silence_timeout_ms)
        # Cap one utterance length so recognize_once doesn't wait forever on near-continuous audio.
        self._segmentation_max_ms = _env_int("DEBATE_STT_SEGMENTATION_MAX_MS", 25000)
        self._end_silence_timeout_ms = _env_int("DEBATE_STT_END_SILENCE_MS", 700)
        self._recognizer_lock = threading.Lock()
        self._listen_lock = threading.Lock()
        self.recognizer = self._build_recognizer()
        logger.info(
            "STT config: initial_silence=%sms segmentation_silence=%sms segmentation_max=%sms end_silence=%sms",
            self._initial_silence_timeout_ms,
            self._silence_timeout_ms,
            self._segmentation_max_ms,
            self._end_silence_timeout_ms,
        )

        # ── Echo suppression state ─────────────────────────────────────────────
        self._muted_until = 0.0  # epoch time until which we ignore audio
        self._mute_lock = threading.Lock()
        self._stop_event = threading.Event()

    def _build_recognizer(self) -> speechsdk.SpeechRecognizer:
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region,
        )

        # ── Silence detection tuning ───────────────────────────────────────────
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs,
            str(self._silence_timeout_ms),
        )
        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
            str(self._initial_silence_timeout_ms),
        )
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationMaximumTimeMs,
            str(self._segmentation_max_ms),
        )
        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
            str(self._end_silence_timeout_ms),
        )

        # ── Use MacBook default microphone ─────────────────────────────────────
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        return speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

    def _reset_recognizer(self, reason: str) -> None:
        logger.warning("Resetting STT recognizer: %s", reason)
        with self._recognizer_lock:
            old = self.recognizer
            try:
                old.stop_continuous_recognition_async()
            except Exception:
                pass
            # Avoid rapid reconnect churn after transport/protocol failures.
            time.sleep(0.2)
            self.recognizer = self._build_recognizer()

    # ── Public API ─────────────────────────────────────────────────────────────

    def mute_for(self, seconds: float):
        """
        Call this right before our own TTS starts speaking so we don't
        pick up our own voice as the opponent's input.
        """
        with self._mute_lock:
            self._muted_until = time.time() + seconds

    def stop(self):
        """
        Signal listener shutdown so blocking waits can unwind quickly.
        Safe to call multiple times.
        """
        self._stop_event.set()
        with self._recognizer_lock:
            try:
                # Defensive: only affects continuous mode, but harmless here.
                self.recognizer.stop_continuous_recognition_async()
            except Exception:
                pass

    def close(self):
        self.stop()

    def listen_for_turn(self, timeout_seconds: int = 60) -> str:
        """
        Block until opponent speech is recognized (or timeout).
        Returns the recognized text, or "" if nothing heard.
        """
        # Wait if we're in mute window (echo suppression)
        deadline = time.time() + timeout_seconds
        while True:
            if self._stop_event.is_set():
                return ""
            with self._mute_lock:
                if time.time() >= self._muted_until:
                    break
            if time.time() >= deadline:
                return ""
            time.sleep(0.05)

        logger.info("Listening for opponent")

        with self._listen_lock:
            with self._recognizer_lock:
                recognizer = self.recognizer

            try:
                result = recognizer.recognize_once_async().get()
            except Exception as exc:
                detail = str(exc)
                logger.warning("STT recognize_once failed: %s", detail)
                if "SPXERR_START_RECOGNIZING_INVALID_STATE_TRANSITION" in detail:
                    self._reset_recognizer("invalid state transition")
                return ""

            if result is None:
                return ""

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = result.text.strip()
                logger.info("Heard: %s", text)

                # Basic sanity filter — ignore very short noise artifacts
                if len(text.split()) < 2:
                    logger.debug("Speech too short, ignoring")
                    return ""

                return text

            if result.reason == speechsdk.ResultReason.NoMatch:
                logger.info("No speech recognized")
                return ""

            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                logger.warning("STT canceled: %s", details.reason)
                if details.reason == speechsdk.CancellationReason.Error:
                    err_detail = str(details.error_details or "")
                    logger.warning("STT error details: %s", err_detail)
                    if "SPXERR_START_RECOGNIZING_INVALID_STATE_TRANSITION" in err_detail:
                        self._reset_recognizer("invalid state transition")
                return ""

            return ""

    def listen_for_interjection(self) -> str:
        """
        Very short listen - 500ms silence timeout.
        Used to catch interruptions mid-speech.
        """
        if self._stop_event.is_set():
            return ""
        # Temporarily tighten the silence timeout
        # (Azure doesn't support changing it on-the-fly, so we just do recognize_once
        # and return quickly)
        result = self.recognizer.recognize_once_async().get()
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text.strip()
        return ""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    listener = DebateListener()
    print("Say something...")
    text = listener.listen_for_turn()
    print(f"Result: '{text}'")
