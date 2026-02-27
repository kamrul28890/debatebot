"""
src/audio/speaker.py

Azure Neural TTS speaker with persona-specific prosody tuning.
"""

from __future__ import annotations

import logging
import re

import azure.cognitiveservices.speech as speechsdk

from src.config import settings


logger = logging.getLogger(__name__)


# Ordered candidates per persona. The first available voice in the current Azure
# region is used. You can override with:
# - AZURE_TTS_VOICE_TRUMP
# - AZURE_TTS_VOICE_BIDEN
# - AZURE_TTS_VOICE_SISKIND
VOICE_CANDIDATES: dict[str, list[str]] = {
    "trump": [
        "en-US-DavisNeural",        # assertive and energetic
        "en-US-ChristopherNeural",
        "en-US-GuyNeural",
    ],
    "biden": [
        "en-US-RogerNeural",        # calmer, older cadence
        "en-US-GuyNeural",
        "en-US-TonyNeural",
    ],
    "siskind": [
        "en-US-EricNeural",         # crisp, academic moderator tone
        "en-US-TonyNeural",
        "en-US-DavisNeural",
        "en-US-GuyNeural",
    ],
}


TRUMP_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='{voice_name}'>
    <prosody rate='-15%' pitch='+0%' volume='loud'>
      <mstts:express-as style='angry' styledegree='0.6'>
        {text}
      </mstts:express-as>
    </prosody>
  </voice>
</speak>"""

BIDEN_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='{voice_name}'>
    <prosody rate='-8%' pitch='-2%' volume='medium'>
      <mstts:express-as style='friendly' styledegree='0.5'>
        {text}
      </mstts:express-as>
    </prosody>
  </voice>
</speak>"""

SISKIND_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='{voice_name}'>
    <prosody rate='-5%' pitch='-1%' volume='medium'>
      {text}
    </prosody>
  </voice>
</speak>"""

SSML_TEMPLATES = {
    "trump": TRUMP_SSML,
    "biden": BIDEN_SSML,
    "siskind": SISKIND_SSML,
}


class DebateSpeaker:
    """Speaks text via Azure Neural TTS with persona-specific SSML."""

    _voice_inventory: set[str] | None = None

    def __init__(self, persona: str):
        if persona not in VOICE_CANDIDATES:
            raise ValueError(f"Unknown persona: {persona}")
        self.persona = persona

        settings.require_speech()
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region,
        )

        self.voice_name = self._resolve_voice_name(speech_config)
        speech_config.speech_synthesis_voice_name = self.voice_name
        logger.info("[Speaker:%s] Azure voice selected: %s", self.persona, self.voice_name)

        audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        self.synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        self.is_speaking = False

    def speak(self, text: str) -> float:
        """Speak text with persona SSML and return estimated duration in seconds."""
        if not text.strip():
            return 0.0

        self.is_speaking = True
        ssml = self._build_ssml(text)
        logger.info("[%s] %s", self.persona.upper(), text)

        try:
            result = self.synthesizer.speak_ssml_async(ssml).get()
            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                logger.warning("[TTS] Error %s: %s", details.reason, details.error_details)
                self.synthesizer.speak_text_async(text).get()
        except Exception as exc:
            logger.error("[Speaker] Error: %s", exc)
        finally:
            self.is_speaking = False

        word_count = len(text.split())
        return (word_count / 140) * 60

    def speak_async(self, text: str, on_done=None):
        """Non-blocking speak. Calls on_done() when finished."""
        import threading

        def _worker():
            self.speak(text)
            if on_done:
                on_done()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    def stop(self):
        """Stop speaking immediately."""
        try:
            self.synthesizer.stop_speaking_async()
        except Exception:
            pass
        self.is_speaking = False

    def _build_ssml(self, text: str) -> str:
        safe_text = self._escape_xml(text)

        if self.persona == "biden":
            safe_text = safe_text.replace("...", '<break time="400ms"/>...')

        if self.persona == "trump":
            safe_text = re.sub(
                r"\b([A-Z]{2,})\b",
                r"<emphasis level=\"strong\">\1</emphasis>",
                safe_text,
            )

        template = SSML_TEMPLATES.get(self.persona, SISKIND_SSML)
        return template.format(text=safe_text, voice_name=self.voice_name)

    def _resolve_voice_name(self, speech_config: speechsdk.SpeechConfig) -> str:
        override_map = {
            "trump": settings.azure_tts_voice_trump,
            "biden": settings.azure_tts_voice_biden,
            "siskind": settings.azure_tts_voice_siskind,
        }
        candidates: list[str] = []
        if override_map.get(self.persona):
            candidates.append(str(override_map[self.persona]))
        candidates.extend(VOICE_CANDIDATES[self.persona])
        candidates = list(dict.fromkeys(candidates))

        available = self._get_voice_inventory(speech_config)
        if available:
            for voice_name in candidates:
                if voice_name in available:
                    return voice_name
            logger.warning(
                "[Speaker:%s] Preferred voices unavailable in region; using %s",
                self.persona,
                candidates[0],
            )
        return candidates[0]

    @classmethod
    def _get_voice_inventory(cls, speech_config: speechsdk.SpeechConfig) -> set[str]:
        if cls._voice_inventory is not None:
            return cls._voice_inventory

        try:
            probe = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
            result = probe.get_voices_async("").get()
            if result.reason == speechsdk.ResultReason.VoicesListRetrieved:
                inventory: set[str] = set()
                for voice in result.voices:
                    short_name = getattr(voice, "short_name", None) or getattr(voice, "ShortName", None)
                    if short_name:
                        inventory.add(short_name)
                cls._voice_inventory = inventory
                return inventory
        except Exception as exc:
            logger.warning("[Speaker] Could not fetch Azure voice inventory (%s)", exc)

        cls._voice_inventory = set()
        return cls._voice_inventory

    @staticmethod
    def _escape_xml(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )


if __name__ == "__main__":
    print("Testing Trump voice...")
    DebateSpeaker("trump").speak("Nobody builds TTS systems better than us. TREMENDOUS voice.")
    print("\nTesting Biden voice...")
    DebateSpeaker("biden").speak("Look folks... here's the deal. This voice is no malarkey.")
    print("\nTesting Siskind voice...")
    DebateSpeaker("siskind").speak("Gentlemen, please. Moving on.")
