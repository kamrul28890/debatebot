"""
src/moderator/siskind.py

Professor Siskind moderator AI.
- Introduces the debate with an opening monologue
- Announces topic changes
- Issues time warnings
- Interjects to restore order
- Has its own persona (dry, academic, slightly exasperated)
"""

import os
import sys
import time
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import openai
import keys

SISKIND_PROMPT = """You are Professor Jeffrey Mark Siskind, a computer science professor at Purdue University 
who has been roped into moderating this chaotic AI presidential debate between Donald Trump and Joe Biden.

Your personality:
- Dry, academic wit. You find this whole situation slightly absurd but you're a professional.
- Occasionally break character to make a nerdy joke about neural networks or NLP
- You're from the Northeast, formal but not stiff
- You have seen too many terrible student presentations to be rattled by anything
- You subtly let slip that you think Trump's rhetoric is statistically incoherent
- You're mildly impressed when either candidate says something accurate
- You keep time obsessively (you are a professor after all)
- Occasionally reference the course: "As I explained in lecture 4..."

Phrases you use:
- "Gentlemen, please."
- "That's... technically not wrong, but..."
- "According to the data—"
- "We're going to move on now."
- "I've graded worse arguments than that."
- "Mr. [Trump/Biden], your time is up."
- "This is not a graduate seminar, but let's at least try for coherent claims."

Keep all responses to 1-2 sentences. You are a moderator, not a debater.
"""

TOPIC_INTRODUCTIONS = [
    "Our first topic tonight is the economy and inflation. Mr. Trump, you have 30 seconds.",
    "Moving on — we'll discuss immigration and border security. Mr. Biden, your response.",
    "Next topic: foreign policy and America's role in NATO. Mr. Trump.",
    "Gentlemen, we turn to healthcare and social security. Mr. Biden.",
    "Our next topic is crime and public safety. I expect coherent responses. Mr. Trump.",
    "We'll now discuss climate change and energy policy. Mr. Biden.",
    "The topic is democracy and election integrity. And yes, I'm aware of the irony. Mr. Trump.",
    "Final topic: U.S.-China relations and trade. Mr. Biden, you may begin.",
]

WARNINGS = [
    "Fifteen seconds remaining, gentlemen.",
    "Time, please. Wrap up your thought.",
    "Mr. {speaker}, I need you to conclude.",
    "That's time. We're moving on whether you're finished or not.",
]

ORDER_INTERJECTIONS = [
    "Gentlemen. Gentlemen. This is not helpful.",
    "Please. I've seen better debate behavior in my undergraduate AI class.",
    "One at a time. This is a debate, not a neural network diverging.",
    "Mr. Trump. Mr. Biden. We have rules.",
    "I'm going to need both of you to stop. Now.",
    "As I said in lecture — structure matters. Please use some.",
]

OPENING_MONOLOGUE = """Good evening. I'm Professor Jeffrey Siskind from Purdue University's 
ECE department, and I have been asked — against my better judgment — to moderate tonight's 
AI presidential debate. The candidates have been trained on public domain speech data 
and will be evaluated on coherence, factual accuracy, and staying under 50 words per response. 
Two of those three metrics I expect to be violated immediately. Let's begin."""


class SiskindModerator:
    """
    Moderator AI with timer enforcement and interjections.
    """

    def __init__(self, tts_callback=None):
        """
        tts_callback: function(text) that speaks the given text
        """
        self.client = openai.AzureOpenAI(
            api_key=keys.azure_openai_key,
            api_version=keys.azure_openai_api_version,
            azure_endpoint=keys.azure_openai_endpoint,
        )
        self.deployment = keys.azure_openai_deployment
        self.tts_callback = tts_callback
        self.topic_index = 0
        self.timer_thread = None
        self.timer_active = False
        self.current_speaker = None

    # ── Public API ─────────────────────────────────────────────────────────────

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
            text = "Gentlemen, we've covered everything. Final thoughts, please. Thirty seconds each."
        self._speak(text)
        return text

    def restore_order(self) -> str:
        """Called when both candidates are talking at once."""
        import random
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
                timeout = f"That's time, {speaker.title()}. We're moving on."
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
            print(f"[Siskind Error] {e}")
            return ""

    # ── Internal ───────────────────────────────────────────────────────────────

    def _speak(self, text: str):
        print(f"[SISKIND] {text}")
        if self.tts_callback:
            self.tts_callback(text)


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def fake_tts(text):
        print(f"  >> TTS: {text}")

    mod = SiskindModerator(tts_callback=fake_tts)
    mod.open_debate()
    time.sleep(1)
    mod.introduce_topic()
    time.sleep(1)
    mod.restore_order()
