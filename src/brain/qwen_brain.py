"""
src/brain/qwen_brain.py

Qwen 2.5 0.5B brain for debate responses.
Supports both local models and Hugging Face Hub models.

Usage:
    brain = QwenBrain(persona="trump")
    response = brain.generate_response("Hello, how are you?")
"""

import os
import json
import re
import torch
from pathlib import Path
from typing import Optional
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM
)
from peft import PeftModel
import logging

logger = logging.getLogger(__name__)

class QwenBrain:
    """
    Qwen 2.5 0.5B model for generating debate responses.

    Supports:
    - Local LoRA adapters
    - Hugging Face Hub models
    - Automatic fallback from local to HF Hub
    """

    def __init__(self, persona: str, model_repo: Optional[str] = None):
        """
        Initialize Qwen brain.

        Args:
            persona: "trump" or "biden"
            model_repo: Optional HF Hub repo name. If None, uses default.
        """
        self.persona = persona
        self.base_dir = Path(__file__).parent.parent.parent
        self.models_dir = self.base_dir / "data" / "models"

        # Optional persona-specific fallback repos. Kept empty by default so
        # runtime behavior is explicit unless user configures HF env vars.
        self.default_repos = {
            "trump": None,
            "biden": None,
        }

        env_repo = (
            os.getenv(f"HF_MODEL_REPO_{persona.upper()}") or
            os.getenv("HF_MODEL_REPO")
        )

        # Use provided repo or default
        self.model_repo = model_repo or env_repo or self.default_repos.get(persona)

        # Local model path
        self.local_model_path = self.models_dir / f"qwen-2.5-0.5b-finetuned-{persona}"

        self.model = None
        self.tokenizer = None
        self.max_new_tokens = int(os.getenv("DEBATE_QWEN_MAX_NEW_TOKENS", "88"))
        self.temperature = float(os.getenv("DEBATE_QWEN_TEMPERATURE", "0.58"))
        self.top_p = float(os.getenv("DEBATE_QWEN_TOP_P", "0.9"))
        self.repetition_penalty = float(os.getenv("DEBATE_QWEN_REPETITION_PENALTY", "1.18"))
        self.no_repeat_ngram_size = int(os.getenv("DEBATE_QWEN_NO_REPEAT_NGRAM", "3"))

        # Load model
        self._load_model()

    def _load_model(self):
        """Load model from local path or HF Hub."""
        try:
            # Try local model first
            if self.local_model_path.exists():
                logger.info(f"Loading local model: {self.local_model_path}")
                self._load_local_model()
            else:
                if not self.model_repo:
                    raise ValueError(f"No local model and no HF repo configured for persona: {self.persona}")
                logger.info(f"Local model not found, loading from HF Hub: {self.model_repo}")
                self._load_hf_model()

            if self.model is not None:
                self.model.eval()

            logger.info("✅ Qwen model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Qwen model: {e}")
            raise

    def _load_local_model(self):
        """Load model from local directory (with LoRA adapters)."""
        base_model_source = self._resolve_base_model_source()
        logger.info(f"Using base model source: {base_model_source}")

        # Load base model
        self.tokenizer = AutoTokenizer.from_pretrained(
            base_model_source,
            trust_remote_code=True
        )

        # Load base model
        self.model = AutoModelForCausalLM.from_pretrained(
            base_model_source,
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True
        )

        # Load LoRA adapters
        self.model = PeftModel.from_pretrained(
            self.model,
            str(self.local_model_path),
            torch_dtype=torch.float32
        )

        # Merge LoRA weights for inference
        self.model = self.model.merge_and_unload()

    def _resolve_base_model_source(self) -> str:
        """
        Resolve the base model source for local LoRA adapters.

        Priority:
        1. QWEN_BASE_MODEL env var (path or HF repo)
        2. base_model_name_or_path from adapter_config.json
        3. Local path if it contains config.json
        4. Official Qwen base model repo
        """
        env_source = os.getenv("QWEN_BASE_MODEL")
        if env_source:
            return env_source

        # Adapter metadata usually stores the correct base model repo.
        adapter_config = self.local_model_path / "adapter_config.json"
        if adapter_config.exists():
            try:
                with open(adapter_config, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                adapter_source = cfg.get("base_model_name_or_path")
                if adapter_source:
                    return str(adapter_source)
            except Exception as e:
                logger.warning(f"Could not read adapter_config.json: {e}")

        # Optional local full model mirror (must be a real HF model folder).
        local_base = self.models_dir / "qwen-2.5-0.5b-base"
        if (local_base / "config.json").exists():
            return str(local_base)

        return "Qwen/Qwen2.5-0.5B"

    def _load_hf_model(self):
        """Load model from Hugging Face Hub."""
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_repo,
            trust_remote_code=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_repo,
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True
        )

    def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """
        Generate a response to the given prompt.

        Args:
            prompt: The input prompt (opponent's statement)
            context: Optional additional context (RAG quotes, etc.)

        Returns:
            Generated response text
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model not loaded")

        # Build full prompt
        full_prompt = self._build_prompt(prompt, context)

        try:
            inputs = self.tokenizer(
                full_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=768,
            )

            with torch.no_grad():
                output_ids = self.model.generate(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    max_new_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    do_sample=True,
                    repetition_penalty=self.repetition_penalty,
                    no_repeat_ngram_size=self.no_repeat_ngram_size,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )

            prompt_len = inputs["input_ids"].shape[1]
            new_tokens = output_ids[0][prompt_len:]
            response = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

            # Clean up response
            response = self._clean_response(response)

            return response

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return "I apologize, but I'm having trouble generating a response right now."

    def _build_prompt(self, prompt: str, context: Optional[str] = None) -> str:
        """Build the full prompt for generation."""
        # Base system prompt (persona-specific)
        system_prompts = {
            "trump": (
                "You are Donald J. Trump in a presidential debate. "
                "Respond confidently, use simple language, directly answer the question, "
                "include at least one concrete claim or example, and challenge the opponent's point. "
                "Do not praise or endorse your opponent."
            ),
            "biden": (
                "You are Joe Biden in a presidential debate. "
                "Respond thoughtfully, directly answer the question, "
                "include at least one concrete policy or factual detail, and challenge the opponent's point. "
                "Do not praise or endorse your opponent."
            ),
        }

        system = system_prompts.get(self.persona, "You are in a presidential debate.")

        full_prompt = f"System: {system}\n\n"

        if context:
            full_prompt += f"Context: {context}\n\n"

        full_prompt += (
            "Answer the moderator's question directly, stay on that exact topic, "
            "and rebut the opponent's main claim. Do not output labels or instructions.\n\n"
        )
        full_prompt += f"Debate prompt: {prompt}\n\nYou:"

        return full_prompt

    def _clean_response(self, response: str) -> str:
        """Clean up the generated response."""
        # Remove prompt scaffolding that may leak from the model.
        artifacts = [
            "System:",
            "Context:",
            "Opponent:",
            "Debate prompt:",
            "Task:",
            "Instruction:",
            "You:",
            "Response:",
            "Answer:",
        ]
        for artifact in artifacts:
            if artifact in response:
                response = response.split(artifact)[0].strip()

        response = self._dedupe_sentences(response)
        response = re.sub(
            r"\b(you are up|your turn|over to you)\b\.?$",
            "",
            response,
            flags=re.IGNORECASE,
        ).strip()

        # Limit length
        if len(response) > 500:
            response = response[:500] + "..."

        if response and response[-1] not in ".!?":
            response += "."
        return response.strip()

    @staticmethod
    def _dedupe_sentences(text: str) -> str:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
        if not sentences:
            return text.strip()

        seen: dict[str, int] = {}
        kept: list[str] = []
        for sentence in sentences:
            norm = re.sub(r"[^a-z0-9\s]", "", sentence.lower()).strip()
            if not norm:
                continue
            count = seen.get(norm, 0)
            if count >= 1 and len(norm.split()) >= 3:
                continue
            seen[norm] = count + 1
            kept.append(sentence)

        merged = " ".join(kept).strip()
        return merged if merged else text.strip()

    def unload_model(self):
        """Unload model from memory."""
        if self.model:
            del self.model
            del self.tokenizer
            torch.cuda.empty_cache()  # Even though we're on CPU
            self.model = None
            self.tokenizer = None
            logger.info("Model unloaded from memory")
