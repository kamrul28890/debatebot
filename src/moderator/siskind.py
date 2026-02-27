"""
src/moderator/siskind.py

Professor Siskind moderator AI.
- Introduces the debate with an opening monologue
- Announces topic changes
- Issues time warnings
- Interjects to restore order
- Has its own persona (dry, academic, slightly exasperated)
"""

from __future__ import annotations

import logging
import random
import threading
import time

import openai

from src.config import settings


logger = logging.getLogger(__name__)

SISKIND_PROMPT = """You are Professor Jeffrey Mark Siskind, a computer science professor at Purdue University
who has been roped into moderating this chaotic AI presidential debate between Donald Trump and Joe Biden.

Your personality:
- Dry, academic wit. You find this whole situation slightly absurd but you're a professional.
- Occasionally break character to make a nerdy joke about neural networks or NLP.
- Formal but not stiff.
- You keep time obsessively.
- You enforce concise answers and clear structure.

Phrases you use:
- "Gentlemen, please."
- "That is technically not wrong, but..."
- "According to the data-"
- "We are going to move on now."
- "I have graded worse arguments than that."
- "Mr. [Trump/Biden], your time is up."

Keep responses to 1-2 sentences. You are a moderator, not a debater.
"""

TOPIC_INTRODUCTIONS = [
    "Round one: economy, inflation, and wages. Mr. Trump, thirty seconds.",
    "Round two: immigration, border enforcement, and asylum processing. Mr. Biden.",
    "Round three: healthcare costs, prescription drugs, and Medicare stability. Mr. Trump.",
    "Round four: wars abroad, NATO commitments, and U.S. deterrence strategy. Mr. Biden.",
    "Round five: Epstein file transparency and accountability for powerful people. Mr. Trump.",
    "Round six: Hunter Biden pardon ethics and Justice Department independence. Mr. Biden.",
    "Round seven: presidential legal exposure, election integrity, and rule of law. Mr. Trump.",
    "Round eight: China competition, trade resilience, debt, and industrial policy. Mr. Biden.",
]

WARNINGS = [
    "Fifteen seconds remaining, gentlemen.",
    "Time, please. Wrap up your thought.",
    "Mr. {speaker}, I need you to conclude.",
    "That is time. We are moving on whether you are finished or not.",
]

ORDER_INTERJECTIONS = [
    "Gentlemen. Gentlemen. This is not helpful.",
    "Please. I have seen better debate behavior in my undergraduate AI class.",
    "One at a time. This is a debate, not a neural network diverging.",
    "Mr. Trump. Mr. Biden. We have rules.",
    "I am going to need both of you to stop. Now.",
    "As I said in lecture - structure matters. Please use some.",
]

OPENING_MONOLOGUE = """Good evening. I am Professor Jeffrey Siskind from Purdue ECE, moderating this AI debate.
Format tonight: alternating thirty-second turns, roughly eight rounds per candidate, with strict topic discipline.
I care about coherence, factual support, and complete answers. Please treat those as hard constraints, not suggestions."""


class SiskindModerator:
    """
    Moderator AI with timer enforcement and interjections.
    """

    def __init__(self, tts_callback=None):
        """
        tts_callback: function(text) that speaks the given text
        """
        settings.require_openai()
        self.client = openai.AzureOpenAI(
            api_key=settings.azure_openai_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self.deployment = settings.azure_openai_deployment
        self.tts_callback = tts_callback
        self.topic_index = 0
        self.timer_thread = None
        self.timer_active = False
        self.current_speaker = None

    # Public API
    def open_debate(self) -> str:
        """Returns + speaks the opening monologue."""
        self._speak(OPENING_MONOLOGUE)
        return OPENING_MONOLOGUE

    def introduce_topic(self) -> str:
        """Introduces the next debate topic."""
        if self.topic_index < len(TOPIC_INTRODUCTIONS):
            text = TOPIC_INTRODUCTIONS[self.topic_index]
            self.topic_index += 1
        else:
            text = "We have covered all rounds. Final closing thought, thirty seconds each."
        self._speak(text)
        return text

    def restore_order(self) -> str:
        """Called when both candidates are talking at once."""
        text = random.choice(ORDER_INTERJECTIONS)
        self._speak(text)
        return text

    def start_timer(self, speaker: str, seconds: int = 30, warning_at: int = 15):
        """
        Start a countdown timer for a speaker.
        Fires a warning at warning_at seconds, then calls time at 0.
        """
        self.timer_active = True
        self.current_speaker = speaker

        def _timer_worker():
            time.sleep(seconds - warning_at)
            if self.timer_active:
                warning = f"Fifteen seconds remaining, {speaker.title()}."
                self._speak(warning)
                time.sleep(warning_at)
            if self.timer_active:
                timeout = f"That is time, {speaker.title()}. We are moving on."
                self._speak(timeout)
                self.timer_active = False

        self.timer_thread = threading.Thread(target=_timer_worker, daemon=True)
        self.timer_thread.start()

    def stop_timer(self):
        """Called when speaker finishes before time is up."""
        self.timer_active = False

    def generate_comment(self, statement: str) -> str:
        """
        Generate a dry Siskind-style comment on a statement.
        Used sparingly for extra flavor.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": SISKIND_PROMPT},
                    {"role": "user", "content": f"React briefly to this debate statement: '{statement}'"},
                ],
                max_tokens=60,
                temperature=0.7,
            )
            text = response.choices[0].message.content.strip()
            self._speak(text)
            return text
        except Exception as e:
            logger.warning("[Siskind] Error: %s", e)
            return ""

    # Internal
    def _speak(self, text: str):
        logger.info("[SISKIND] %s", text)
        if self.tts_callback:
            self.tts_callback(text)


# Standalone test
if __name__ == "__main__":
    def fake_tts(text):
        print(f"  >> TTS: {text}")

    mod = SiskindModerator(tts_callback=fake_tts)
    mod.open_debate()
    time.sleep(1)
    mod.introduce_topic()
    time.sleep(1)
    mod.restore_order()
