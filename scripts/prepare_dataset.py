#!/usr/bin/env python3
"""
scripts/prepare_dataset.py

Helper script to prepare training data for Qwen fine-tuning.

Usage:
    python scripts/prepare_dataset.py --input_file your_data.txt --output_file biden_train.jsonl

Input formats supported:
1. Plain text file (one conversation per line)
2. JSONL with "text" field already
3. Raw speech transcripts

Output: JSONL format suitable for Qwen training
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

def load_text_file(file_path: str) -> List[str]:
    """Load a plain text file, one conversation per line."""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines

def load_jsonl_file(file_path: str) -> List[Dict[str, Any]]:
    """Load existing JSONL file."""
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line.strip()))
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON line: {e}")
    return data

def convert_to_instruction_format(text: str, persona: str) -> Dict[str, str]:
    """
    Convert raw text to instruction-response format.

    This is a simple converter - you may need to customize based on your data.
    """
    # For debate training, we want the model to respond as the persona
    # Format: "Opponent said: [text]" -> "You (as persona) respond: [response]"

    # This is a placeholder - you'll need to format your data properly
    # For now, we'll just wrap it in a simple instruction format

    instruction = f"You are {persona.title()} in a presidential debate. Respond to the following statement from your opponent:"

    return {
        "instruction": instruction,
        "input": text,
        "output": ""  # You'll need to provide the expected response
    }

def prepare_dataset(input_file: str, output_file: str, persona: str, format_type: str = "auto"):
    """Prepare dataset for training."""

    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Determine input format
    if format_type == "auto":
        if input_path.suffix.lower() == ".jsonl":
            format_type = "jsonl"
        else:
            format_type = "text"

    # Load data
    if format_type == "jsonl":
        data = load_jsonl_file(str(input_path))
        print(f"Loaded {len(data)} existing JSONL entries")
    else:
        lines = load_text_file(str(input_path))
        print(f"Loaded {len(lines)} text lines")

        # Convert to instruction format
        data = []
        for line in lines:
            if len(line) > 10:  # Skip very short lines
                entry = convert_to_instruction_format(line, persona)
                data.append(entry)

    # Validate and save
    valid_data = []
    for i, item in enumerate(data):
        if "text" in item or ("instruction" in item and "output" in item):
            valid_data.append(item)
        else:
            print(f"Warning: Skipping invalid entry {i}: {item}")

    # Save as JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in valid_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"✅ Saved {len(valid_data)} entries to {output_file}")
    print("\n📝 Note: This is a basic converter. You may need to:")
    print("   1. Add proper 'output' fields with expected responses")
    print("   2. Format conversations as instruction-response pairs")
    print("   3. Clean and filter your training data")
    print("   4. Consider using a more sophisticated data preparation pipeline")

def main():
    parser = argparse.ArgumentParser(description="Prepare dataset for Qwen fine-tuning")
    parser.add_argument("--input_file", required=True, help="Input data file")
    parser.add_argument("--output_file", required=True, help="Output JSONL file")
    parser.add_argument("--persona", required=True, choices=["trump", "biden"], help="Target persona")
    parser.add_argument("--format", choices=["auto", "text", "jsonl"], default="auto",
                       help="Input format (auto-detects by extension)")

    args = parser.parse_args()

    try:
        prepare_dataset(args.input_file, args.output_file, args.persona, args.format)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()