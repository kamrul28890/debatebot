#!/usr/bin/env python3
"""
scripts/finetune_qwen.py

Fine-tune Qwen 2.5 0.5B model using LoRA on CPU.

Usage:
    python scripts/finetune_qwen.py --persona trump
    python scripts/finetune_qwen.py --persona biden
    python scripts/finetune_qwen.py --persona both

Dataset format expected:
    data/biden_train.jsonl or data/trump_train.jsonl
    Each line: {"text": "full conversation or instruction-response pair"}

Output:
    - Saves LoRA adapters to data/models/qwen-2.5-0.5b-finetuned-{persona}/
    - Can be uploaded to Hugging Face Hub
"""

import os
import sys
import json
import argparse
from pathlib import Path
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import Dataset
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
BASE_MODEL = "Qwen/Qwen2.5-0.5B"
MAX_SEQ_LENGTH = 512
BATCH_SIZE = 2  # Small for CPU
GRADIENT_ACCUMULATION_STEPS = 4
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.1

class QwenFineTuner:
    def __init__(self, persona: str):
        self.persona = persona
        self.base_dir = Path(__file__).parent.parent
        self.data_dir = self.base_dir / "data"
        self.models_dir = self.data_dir / "models"

        # Create directories
        self.models_dir.mkdir(exist_ok=True)

        # Model paths
        self.base_model_path = self.models_dir / "qwen-2.5-0.5b-base"
        self.output_dir = self.models_dir / f"qwen-2.5-0.5b-finetuned-{persona}"

        logger.info(f"Base model path: {self.base_model_path}")
        logger.info(f"Output path: {self.output_dir}")

    def load_dataset(self) -> Dataset:
        """Load and prepare dataset for training."""
        dataset_files = []

        if self.persona in ["trump", "biden"]:
            data_file = self.data_dir / f"{self.persona}_train.jsonl"
            if not data_file.exists():
                raise FileNotFoundError(f"Dataset not found: {data_file}")
            dataset_files.append(str(data_file))
        elif self.persona == "both":
            for p in ["trump", "biden"]:
                data_file = self.data_dir / f"{p}_train.jsonl"
                if data_file.exists():
                    dataset_files.append(str(data_file))
                else:
                    logger.warning(f"Dataset not found: {data_file}")

        if not dataset_files:
            raise FileNotFoundError("No dataset files found!")

        logger.info(f"Loading datasets: {dataset_files}")

        # Load JSONL files
        all_data = []
        for file_path in dataset_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            item = json.loads(line.strip())
                            if "text" in item:
                                all_data.append({"text": item["text"]})
                            elif "messages" in item:
                                # Convert the messages array into Qwen's expected chat format
                                text_block = ""
                                for msg in item["messages"]:
                                    text_block += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
                                all_data.append({"text": text_block})
                            elif "instruction" in item:
                                # Convert instruction-style rows into a single training text.
                                instruction = (item.get("instruction") or "").strip()
                                input_text = (item.get("input") or "").strip()
                                output_text = (item.get("output") or "").strip()
                                if output_text:
                                    merged = f"Instruction: {instruction}\nInput: {input_text}\nResponse: {output_text}"
                                    all_data.append({"text": merged})
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping invalid JSON line: {e}")

        if not all_data:
            raise ValueError("No valid training data found!")

        logger.info(f"Loaded {len(all_data)} training examples")
        return Dataset.from_list(all_data)

    def tokenize_function(self, examples, tokenizer):
        """Tokenize the dataset."""
        return tokenizer(
            examples["text"],
            truncation=True,
            padding="max_length",
            max_length=MAX_SEQ_LENGTH,
        )

    def setup_model_and_tokenizer(self):
        """Load model and tokenizer with LoRA configuration."""
        logger.info("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            BASE_MODEL,
            trust_remote_code=True,
            cache_dir=str(self.base_model_path)
        )

        # Add padding token if not exists
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        logger.info("Loading model...")
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.float32,  # Use float32 for CPU
            device_map="cpu",  # Force CPU
            trust_remote_code=True,
            cache_dir=str(self.base_model_path)
        )

        logger.info("Setting up LoRA...")
        # LoRA configuration
        lora_config = LoraConfig(
            r=LORA_R,
            lora_alpha=LORA_ALPHA,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_dropout=LORA_DROPOUT,
            bias="none",
            task_type="CAUSAL_LM",
        )

        # Prepare model for training
        model = prepare_model_for_kbit_training(model)
        model = get_peft_model(model, lora_config)

        model.print_trainable_parameters()

        return model, tokenizer

    def train(self):
        """Main training function."""
        logger.info(f"Starting fine-tuning for persona: {self.persona}")

        # Load dataset
        dataset = self.load_dataset()

        # Setup model and tokenizer
        model, tokenizer = self.setup_model_and_tokenizer()

        # Tokenize dataset
        logger.info("Tokenizing dataset...")
        tokenized_dataset = dataset.map(
            lambda x: self.tokenize_function(x, tokenizer),
            batched=True,
            remove_columns=["text"]
        )

        # Data collator
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=tokenizer,
            mlm=False,  # Causal LM, not masked LM
        )

        # Training arguments
        training_args = TrainingArguments(
            output_dir=str(self.output_dir),
            num_train_epochs=NUM_EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
            learning_rate=LEARNING_RATE,
            weight_decay=0.01,
            logging_steps=10,
            save_steps=100,
            save_total_limit=2,
            evaluation_strategy="no",
            load_best_model_at_end=False,
            fp16=False,  # No FP16 on CPU
            bf16=False,  # No BF16 on CPU
            dataloader_num_workers=0,  # Avoid multiprocessing issues
            remove_unused_columns=False,
        )

        # Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            data_collator=data_collator,
        )

        # Train
        logger.info("Starting training...")
        trainer.train()

        # Save the model
        logger.info(f"Saving model to {self.output_dir}")
        trainer.save_model(str(self.output_dir))
        tokenizer.save_pretrained(str(self.output_dir))

        logger.info("Training completed successfully!")
        logger.info(f"Model saved to: {self.output_dir}")
        logger.info("You can now upload this to Hugging Face Hub using:")
        logger.info(f"python scripts/upload_to_huggingface.py --model_path {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen 2.5 0.5B with LoRA")
    parser.add_argument(
        "--persona",
        choices=["trump", "biden", "both"],
        required=True,
        help="Which persona to train on"
    )

    args = parser.parse_args()

    # Check if datasets exist
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"

    if args.persona in ["trump", "biden"]:
        data_file = data_dir / f"{args.persona}_train.jsonl"
        if not data_file.exists():
            print(f"❌ Dataset not found: {data_file}")
            print("Please place your training data in the data/ directory.")
            sys.exit(1)
    elif args.persona == "both":
        trump_file = data_dir / "trump_train.jsonl"
        biden_file = data_dir / "biden_train.jsonl"
        if not trump_file.exists() and not biden_file.exists():
            print("❌ No datasets found. Please place trump_train.jsonl and/or biden_train.jsonl in data/")
            sys.exit(1)

    # Start training
    trainer = QwenFineTuner(args.persona)
    trainer.train()


if __name__ == "__main__":
    main()
