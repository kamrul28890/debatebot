"""
src/brain/model.py

The DebateBrain: GPT-4 powered persona engine with:
- Rich persona prompts loaded from file
- RAG: real quotes injected into context from debate transcripts
- Conversation memory (last 8 turns)
- Automatic topic rotation every 4 turns
- Graceful fallback if RAG unavailable (zero degradation)
"""

import os
import logging
import random
from typing import List, Optional

import openai
from src.config import settings

logger = logging.getLogger(__name__)

# ── Debate topics ──────────────────────────────────────────────────────────────
DEBATE_TOPICS = [
    "the economy and inflation",
    "immigration and border security",
    "foreign policy and NATO",
    "healthcare and social security",
    "crime and public safety",
    "climate change and energy",
    "democracy and the 2020 election",
    "China and trade policy",
]

INTERJECTIONS = {
    "trump": [
        "Wrong.",
        "Excuse me — that's just not true.",
        "Nobody believes that.",
        "False. Totally false.",
        "That's a lie. A total lie.",
    ],
    "biden": [
        "C'mon, man.",
        "That's — look, that's just malarkey.",
        "Not true. Not a word of it's true.",
        "Will you just — will you stop?",
        "Here's what actually happened—",
    ],
}


class DebateBrain:
    """
    Core AI brain for a debate persona.

    Supports multiple LLM backends:
    - "azure": Azure OpenAI (GPT-4) - default
    - "qwen": Local/HF Qwen 2.5 0.5B model

    RAG behavior:
    - Retrieves 3-4 real quotes semantically similar to opponent's statement
    - Injects them as a block: "Here's how you have spoken about this before:"
    - If RAG unavailable/fails -> silently skips, normal prompt used
    - RAG enrichment is purely additive — never replaces or degrades the response
    """

    def __init__(self, persona: str, brain_type: str = "azure"):
        if persona not in ("trump", "biden", "siskind"):
            raise ValueError(f"Unknown persona: {persona}")
        if brain_type not in ("azure", "qwen"):
            raise ValueError(f"Unknown brain type: {brain_type}")

        self.persona = persona
        self.brain_type = brain_type
        self.topic_index = 0
        self.turn_count = 0
        self.rag_hits = 0
        self.rag_misses = 0
        self.qwen_init_error: str | None = None

        # ── Initialize LLM backend ─────────────────────────────────────────────
        if brain_type == "azure":
            self._init_azure_client()
        elif brain_type == "qwen":
            self._init_qwen_client()

        # ── Load persona prompt from file ──────────────────────────────────────
        persona_file = os.path.join(
            os.path.dirname(__file__), "personas", f"{persona}.txt"
        )
        if os.path.exists(persona_file):
            with open(persona_file, "r") as f:
                self.persona_prompt = f.read()
        else:
            self.persona_prompt = (
                f"You are {persona.title()} in a presidential debate. "
                "Keep answers short, punchy, and completely in character."
            )

        # ── RAG retriever (graceful degradation if unavailable) ────────────────
        logger.info("[Brain:%s] Initializing RAG...", persona)
        try:
            from src.brain.rag import RAGRetriever
            self.rag = RAGRetriever(persona)
            if self.rag.is_ready():
                logger.info("[Brain:%s] RAG ready - %s quotes indexed", persona, self.rag.corpus_size())
            else:
                logger.warning("[Brain:%s] RAG not ready - running without retrieval", persona)
        except Exception as e:
            logger.warning("[Brain:%s] RAG init error (%s) - running without retrieval", persona, e)
            self.rag = None

        # ── Conversation history ───────────────────────────────────────────────
        self.history = []

    def _init_azure_client(self):
        """Initialize Azure OpenAI client."""
        settings.require_openai()
        self.client = openai.AzureOpenAI(
            api_key=settings.azure_openai_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self.deployment = settings.azure_openai_deployment

    def _init_qwen_client(self):
        """Initialize Qwen client (with Azure fallback on runtime failure)."""
        try:
            from src.brain.qwen_brain import QwenBrain

            self.qwen_brain = QwenBrain(self.persona)
            self.qwen_init_error = None
        except Exception as exc:
            self.qwen_init_error = str(exc)
            logger.error("[Brain:%s] Qwen init failed: %s", self.persona, exc)
            logger.warning("[Brain:%s] Falling back to Azure backend", self.persona)
            self.brain_type = "azure"
            self._init_azure_client()

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_response(self, opponent_text: str) -> str:
        """
        Generate a debate response to opponent_text.
        RAG quotes are injected into the system prompt if available.
        """
        self.turn_count += 1

        if self.brain_type == "azure":
            return self._generate_azure_response(opponent_text)
        elif self.brain_type == "qwen":
            return self._generate_qwen_response(opponent_text)
        else:
            raise ValueError(f"Unknown brain type: {self.brain_type}")

    def _generate_azure_response(self, opponent_text: str) -> str:
        """Generate response using Azure OpenAI."""
        system_prompt = self._build_system_prompt(opponent_text)
        self.history.append({"role": "user", "content": opponent_text})

        messages = (
            [{"role": "system", "content": system_prompt}]
            + self.history[-8:]     # keep last 8 turns for memory
        )

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                max_tokens=120,
                temperature=0.88,
                top_p=0.95,
                frequency_penalty=0.3,
                presence_penalty=0.1,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error("[Brain:%s] Azure API error: %s", self.persona, e)
            reply = self._fallback_response()

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _generate_qwen_response(self, opponent_text: str) -> str:
        """Generate response using Qwen model."""
        # Build context with RAG
        context = self._get_rag_block(opponent_text)
        if context:
            self.rag_hits += 1
        else:
            self.rag_misses += 1

        # Build conversation history for Qwen
        history_text = ""
        if self.history:
            # Convert last few turns to text format
            recent_turns = self.history[-6:]  # Last 3 exchanges (6 messages)
            for i in range(0, len(recent_turns), 2):
                if i+1 < len(recent_turns):
                    user_msg = recent_turns[i].get("content", "")
                    assistant_msg = recent_turns[i+1].get("content", "")
                    history_text += f"Opponent: {user_msg}\nYou: {assistant_msg}\n\n"

        # Include conversation history in model context.
        context_parts = []
        if context:
            context_parts.append(context)
        if history_text:
            context_parts.append(f"Recent debate history:\n{history_text.strip()}")
        qwen_context = "\n\n".join(context_parts) if context_parts else None

        try:
            reply = self.qwen_brain.generate_response(opponent_text, qwen_context)
        except Exception as e:
            logger.error("[Brain:%s] Qwen generation error: %s", self.persona, e)
            reply = self._fallback_response()

        # Update history
        self.history.append({"role": "user", "content": opponent_text})
        self.history.append({"role": "assistant", "content": reply})

        return reply

    def generate_interjection(self) -> str:
        """Quick one-liner interjection when opponent is still talking."""
        return random.choice(INTERJECTIONS.get(self.persona, ["..."]))

    def get_opening_statement(self) -> str:
        return self.generate_response(
            "Please give your opening statement for this presidential debate."
        )

    def reset(self):
        self.history = []
        self.turn_count = 0
        self.topic_index = 0

    def current_topic(self) -> str:
        return DEBATE_TOPICS[self.topic_index]

    def rag_stats(self) -> dict:
        return {
            "hits": self.rag_hits,
            "misses": self.rag_misses,
            "corpus_size": self.rag.corpus_size() if self.rag else 0,
            "ready": self.rag.is_ready() if self.rag else False,
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _build_system_prompt(self, opponent_text: str) -> str:
        """
        Builds the full system prompt for this turn:
          1. Base persona prompt (from personas/trump.txt etc.)
          2. Topic rotation reminder (every 4 turns)
          3. RAG block with real matching quotes (if available)
        """
        parts = [self.persona_prompt]

        # Rotate topic every 4 turns
        if self.turn_count % 4 == 0 and self.turn_count > 0:
            self.topic_index = (self.topic_index + 1) % len(DEBATE_TOPICS)
            topic = DEBATE_TOPICS[self.topic_index]
            parts.append(
                f"\n[DEBATE NOTE: Steer your answer toward: {topic}.]"
            )

        # RAG injection — purely additive, silent on failure
        rag_block = self._get_rag_block(opponent_text)
        if rag_block:
            parts.append(rag_block)
            self.rag_hits += 1
        else:
            self.rag_misses += 1

        return "\n".join(parts)

    def _get_rag_block(self, query: str) -> Optional[str]:
        """
        Retrieve relevant real quotes and format as a prompt injection block.
        Returns None silently on any failure — never raises.
        """
        if self.rag is None or not self.rag.is_ready():
            return None

        try:
            quotes = self.rag.retrieve(query, k=4)
            if not quotes:
                return None

            lines = [
                "",
                "=== YOUR REAL QUOTES ON THIS TOPIC ===",
                "These are things you have actually said. Use this voice and style:",
            ]
            for i, q in enumerate(quotes, 1):
                lines.append(f'  {i}. "{q}"')
            lines.append("=== END QUOTES ===")
            lines.append("Respond to the debate in your own words, grounded in the above.")

            return "\n".join(lines)

        except Exception as e:
            logger.warning("[Brain:%s] RAG block error (non-fatal): %s", self.persona, e)
            return None

    def _fallback_response(self) -> str:
        fallbacks = {
            "trump": "Look, I'll tell you this — nobody knows more about this than me. Believe me.",
            "biden": "Look, here's the deal — the American people deserve better than this.",
            "siskind": "Gentlemen, please. Let's keep this debate on track.",
        }
        return fallbacks.get(self.persona, "I need a moment.")


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing DebateBrain with RAG...\n")

    trump = DebateBrain("trump")
    print(f"Trump RAG stats: {trump.rag_stats()}\n")

    r1 = trump.generate_response("The economy is struggling under your watch.")
    print(f"TRUMP: {r1}\n")

    biden = DebateBrain("biden")
    r2 = biden.generate_response("Trump claims he had the greatest economy ever.")
    print(f"BIDEN: {r2}\n")

    print(f"\nFinal stats:")
    print(f"  Trump — {trump.rag_stats()}")
    print(f"  Biden — {biden.rag_stats()}")
