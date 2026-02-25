"""
src/audio/speaker.py

Azure Neural TTS speaker with SSML prosody tuning.
- Trump: loud, slow, dramatic pauses, emphasis on key words
- Biden: softer, occasional stutter pauses, trailing off
- Siskind: dry, measured, academic cadence
- Streams audio for low latency
"""

import os
import logging
import re

import azure.cognitiveservices.speech as speechsdk
from src.config import settings

logger = logging.getLogger(__name__)


# ── Voice assignments ──────────────────────────────────────────────────────────
VOICE_MAP = {
    "trump":   "en-US-DavisNeural",    # Authoritative, assertive male voice
    "biden":   "en-US-GuyNeural",      # Warm, measured male voice
    "siskind": "en-US-TonyNeural",     # Clear, professional male voice
}

# ── SSML prosody templates ─────────────────────────────────────────────────────
# Trump: louder, slower rate, heavy emphasis, dramatic pauses
TRUMP_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='en-US-DavisNeural'>
    <prosody rate='-15%' pitch='+0%' volume='loud'>
      <mstts:express-as style='angry' styledegree='0.6'>
        {text}
      </mstts:express-as>
    </prosody>
  </voice>
</speak>"""

# Biden: slightly slower, softer, natural pauses
BIDEN_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='en-US-GuyNeural'>
    <prosody rate='-8%' pitch='-2%' volume='medium'>
      <mstts:express-as style='friendly' styledegree='0.5'>
        {text}
      </mstts:express-as>
    </prosody>
  </voice>
</speak>"""

# Siskind: measured, slightly formal
SISKIND_SSML = """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
    xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
  <voice name='en-US-TonyNeural'>
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
    """
    Speaks text via Azure Neural TTS with persona-specific SSML.
    Blocking call — returns after audio finishes playing.
    """

    def __init__(self, persona: str):
        if persona not in VOICE_MAP:
            raise ValueError(f"Unknown persona: {persona}")
        self.persona = persona

        settings.require_speech()
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region,
        )
        speech_config.speech_synthesis_voice_name = VOICE_MAP[persona]

        # Live speaker output (MacBook speakers)
        audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

        self.synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        self.is_speaking = False

    def speak(self, text: str) -> float:
        """
        Speak text with persona SSML.
        Returns approximate duration in seconds.
        """
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
                # Fallback: plain text (no SSML)
                self.synthesizer.speak_text_async(text).get()
        except Exception as e:
            logger.error("[Speaker] Error: %s", e)
        finally:
            self.is_speaking = False

        # Estimate duration: ~140 words/min baseline
        word_count = len(text.split())
        return (word_count / 140) * 60

    def speak_async(self, text: str, on_done=None):
        """Non-blocking speak. Calls on_done() when finished."""
        import threading
        def _worker():
            duration = self.speak(text)
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

    # ── Internal ───────────────────────────────────────────────────────────────

    def _build_ssml(self, text: str) -> str:
        """Insert text into the SSML template, escaping XML special chars."""
        safe_text = self._escape_xml(text)

        # Add Biden-style trailing pause on ellipsis
        if self.persona == "biden":
            safe_text = safe_text.replace("...", '<break time="400ms"/>...')

        # Add Trump-style emphasis on caps words
        if self.persona == "trump":
            safe_text = re.sub(
                r'\b([A-Z]{2,})\b',
                r'<emphasis level="strong">\1</emphasis>',
                safe_text
            )

        template = SSML_TEMPLATES.get(self.persona, SISKIND_SSML)
        return template.format(text=safe_text)

    @staticmethod
    def _escape_xml(text: str) -> str:
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Trump voice...")
    trump_speaker = DebateSpeaker("trump")
    trump_speaker.speak("Nobody builds TTS systems better than us. It's true, believe me. TREMENDOUS voice.")

    print("\nTesting Biden voice...")
    biden_speaker = DebateSpeaker("biden")
    biden_speaker.speak("Look folks... here's the deal. This voice synthesis is no malarkey. Not a joke.")

    print("\nTesting Siskind voice...")
    siskind_speaker = DebateSpeaker("siskind")
    siskind_speaker.speak("Gentlemen, please. I've graded worse arguments than that. Moving on.")
