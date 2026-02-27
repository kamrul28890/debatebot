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
                    max_new_tokens=96,
                    temperature=0.65,
                    top_p=0.9,
                    do_sample=True,
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
            "trump": "You are Donald J. Trump in a presidential debate. Respond confidently, use simple language, and defend your positions strongly.",
            "biden": "You are Joe Biden in a presidential debate. Respond thoughtfully, focus on policy details, and address your opponent respectfully."
        }

        system = system_prompts.get(self.persona, "You are in a presidential debate.")

        full_prompt = f"System: {system}\n\n"

        if context:
            full_prompt += f"Context: {context}\n\n"

        full_prompt += f"Opponent: {prompt}\n\nYou:"

        return full_prompt

    def _clean_response(self, response: str) -> str:
        """Clean up the generated response."""
        # Remove any system prompts that might have leaked
        response = response.split("System:")[0].strip()
        response = response.split("Context:")[0].strip()
        response = response.split("Opponent:")[0].strip()

        # Remove common artifacts
        artifacts = ["You:", "Response:", "Answer:"]
        for artifact in artifacts:
            if response.startswith(artifact):
                response = response[len(artifact):].strip()

        # Limit length
        if len(response) > 500:
            response = response[:500] + "..."

        return response.strip()

    def unload_model(self):
        """Unload model from memory."""
        if self.model:
            del self.model
            del self.tokenizer
            torch.cuda.empty_cache()  # Even though we're on CPU
            self.model = None
            self.tokenizer = None
            logger.info("Model unloaded from memory")
