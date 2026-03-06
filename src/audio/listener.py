"""
src/audio/listener.py

Azure Speech-to-Text listener, Mac-optimized.
- Handles acoustic echo from the other laptop's speaker
- 1.5s silence timeout for natural speech end-detection
- Filters out self-echo by checking if our own TTS just fired
"""

import logging
import os
import re
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
        self._recognition_language = os.getenv("DEBATE_STT_LANGUAGE", "en-US").strip() or "en-US"
        self._phrase_hints = self._build_phrase_hints()
        self._short_utterance_allowlist = self._build_short_utterance_allowlist()
        self._recognizer_lock = threading.Lock()
        self._listen_lock = threading.Lock()
        self.recognizer = self._build_recognizer()
        logger.info(
            "STT config: language=%s initial_silence=%sms segmentation_silence=%sms segmentation_max=%sms end_silence=%sms phrase_hints=%s short_hints=%s",
            self._recognition_language,
            self._initial_silence_timeout_ms,
            self._silence_timeout_ms,
            self._segmentation_max_ms,
            self._end_silence_timeout_ms,
            len(self._phrase_hints),
            len(self._short_utterance_allowlist),
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
        speech_config.speech_recognition_language = self._recognition_language

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
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        self._attach_phrase_hints(recognizer)
        return recognizer

    def _attach_phrase_hints(self, recognizer: speechsdk.SpeechRecognizer) -> None:
        if not self._phrase_hints:
            return
        try:
            grammar = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
            add_phrase = getattr(grammar, "addPhrase", None) or getattr(grammar, "add_phrase", None)
            if not callable(add_phrase):
                return
            for phrase in self._phrase_hints:
                add_phrase(phrase)
        except Exception as exc:
            logger.debug("STT phrase-hint attach skipped: %s", exc)

    def _build_phrase_hints(self) -> list[str]:
        hints = [
            "Mr Trump",
            "President Trump",
            "Donald Trump",
            "Trump first",
            "Start with Trump",
            "Mr Biden",
            "President Biden",
            "Joe Biden",
            "Biden first",
            "Start with Biden",
            "Moderator",
        ]

        raw_extra = os.getenv("DEBATE_STT_PHRASE_HINTS", "").strip()
        if raw_extra:
            for token in re.split(r"[|,;]", raw_extra):
                clean = token.strip()
                if clean:
                    hints.append(clean)

        deduped: list[str] = []
        seen: set[str] = set()
        for phrase in hints:
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(phrase)
        return deduped

    def _build_short_utterance_allowlist(self) -> set[str]:
        tokens = {
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
        raw_extra = os.getenv("DEBATE_STT_SHORT_HINTS", "").strip()
        if raw_extra:
            for token in re.split(r"[|,;]", raw_extra):
                clean = re.sub(r"[^a-z0-9]+", "", token.lower())
                if clean:
                    tokens.add(clean)
        return tokens

    def _is_allowed_short_utterance(self, text: str) -> bool:
        words = re.findall(r"[a-z0-9]+", (text or "").lower())
        return len(words) == 1 and words[0] in self._short_utterance_allowlist

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

    @staticmethod
    def _recognize_once_with_timeout(recognizer: speechsdk.SpeechRecognizer, timeout_seconds: float):
        done = threading.Event()
        payload: dict[str, object] = {"result": None, "error": None}

        def _worker() -> None:
            try:
                payload["result"] = recognizer.recognize_once_async().get()
            except Exception as exc:
                payload["error"] = exc
            finally:
                done.set()

        threading.Thread(target=_worker, daemon=True).start()
        if not done.wait(timeout=max(0.2, float(timeout_seconds))):
            raise TimeoutError(f"recognize_once timeout after {timeout_seconds:.1f}s")
        err = payload["error"]
        if isinstance(err, Exception):
            raise err
        if err is not None:
            raise RuntimeError(str(err))
        return payload["result"]

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
                remaining = max(0.1, deadline - time.time())
                result = self._recognize_once_with_timeout(recognizer, timeout_seconds=remaining)
            except TimeoutError:
                logger.info("STT listen timeout reached after %.1fs", timeout_seconds)
                self._reset_recognizer("listen timeout")
                return ""
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
                # except explicit one-word moderator/topic cues (e.g. "economy").
                if len(text.split()) < 2 and not self._is_allowed_short_utterance(text):
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
                    lowered = err_detail.lower()
                    if (
                        "spxerr_start_recognizing_invalid_state_transition" in lowered
                        or "could not validate speech context" in lowered
                        or "error code: 1007" in lowered
                    ):
                        self._reset_recognizer("azure speech context/state error")
                        time.sleep(0.25)
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
