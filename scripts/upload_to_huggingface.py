#!/usr/bin/env python3
"""
scripts/upload_to_huggingface.py

Upload fine-tuned Qwen model to Hugging Face Hub.

Usage:
    python scripts/upload_to_huggingface.py --model_path data/models/qwen-2.5-0.5b-finetuned-trump --repo_name your-username/qwen-debate-trump

Requirements:
    - huggingface_hub installed
    - HF_TOKEN environment variable or logged in with `huggingface-cli login`
"""

import os
import sys
import argparse
from pathlib import Path
from huggingface_hub import HfApi, upload_folder
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_model(model_path: str, repo_name: str):
    """Upload model to Hugging Face Hub."""

    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    # Check if it's a LoRA model (has adapter_config.json)
    adapter_config = model_path / "adapter_config.json"
    is_lora = adapter_config.exists()

    logger.info(f"Uploading {'LoRA ' if is_lora else ''}model from {model_path}")
    logger.info(f"Target repository: {repo_name}")

    # Initialize API
    api = HfApi()

    # Create repository if it doesn't exist
    try:
        api.repo_info(repo_name)
        logger.info("Repository already exists")
    except Exception:
        logger.info("Creating new repository...")
        api.create_repo(repo_name, private=False)
        logger.info(f"Created repository: https://huggingface.co/{repo_name}")

    # Upload the model
    logger.info("Uploading model files...")
    upload_folder(
        folder_path=str(model_path),
        repo_id=repo_name,
        repo_type="model",
    )

    logger.info("✅ Upload completed successfully!")
    logger.info(f"Model available at: https://huggingface.co/{repo_name}")

    # Print usage instructions
    print("\n" + "="*60)
    print("MODEL UPLOAD COMPLETE!")
    print("="*60)
    print(f"Repository: https://huggingface.co/{repo_name}")
    print()
    print("To use this model in the debate app:")
    print("1. Set HF_MODEL_REPO_TRUMP and HF_MODEL_REPO_BIDEN (preferred)")
    print("2. Or set HF_MODEL_REPO for a single shared fallback repo")
    print("3. Restart the debate application")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description="Upload Qwen model to Hugging Face Hub")
    parser.add_argument(
        "--model_path",
        required=True,
        help="Path to the fine-tuned model directory"
    )
    parser.add_argument(
        "--repo_name",
        required=True,
        help="Hugging Face repository name (e.g., 'your-username/qwen-debate-trump')"
    )

    args = parser.parse_args()

    # Check if HF_TOKEN is set
    if not os.getenv("HF_TOKEN") and not os.getenv("HUGGINGFACE_TOKEN"):
        print("⚠️  Warning: No Hugging Face token found!")
        print("Please set HF_TOKEN environment variable or run:")
        print("huggingface-cli login")
        print()

    try:
        upload_model(args.model_path, args.repo_name)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
