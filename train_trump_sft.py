import argparse
import os
import random
from typing import Dict, List

import torch
from datasets import load_dataset
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_OUTPUT_DIR = "outputs/sft_trump"
DEFAULT_DATASET_ID = "meoconxinhxan/trump-speech-dataset-tts"
DEFAULT_DATASET_CONFIG = None
DEFAULT_TRAIN_SPLIT = "train"
DEFAULT_TEXT_FIELD = "text"
DEFAULT_TITLE_FIELD = "title"
DEFAULT_MAX_LENGTH = 1536
DEFAULT_BATCH_SIZE = 1
DEFAULT_GRAD_ACCUM = 8
DEFAULT_EPOCHS = 1
DEFAULT_LR = 2e-5
DEFAULT_SEED = 42
DEFAULT_NUM_TRAIN_EXAMPLES = None
DEFAULT_MAX_STEPS = 1200


def get_hf_cache_dir():
    cache_dir = os.environ.get("HF_CACHE_DIR", "").strip()
    return cache_dir or None


def load_tokenizer(model_id: str, cache_dir=None) -> AutoTokenizer:
    try:
        return AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir, fix_mistral_regex=True)
    except TypeError:
        return AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)


def parse_args():
    p = argparse.ArgumentParser(description="SFT on Trump speech dataset (text-to-speech transcripts).")
    p.add_argument("--model_id", type=str, default=DEFAULT_MODEL_ID)
    p.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--dataset_id", type=str, default=DEFAULT_DATASET_ID)
    p.add_argument("--dataset_config", type=str, default=DEFAULT_DATASET_CONFIG)
    p.add_argument("--train_split", type=str, default=DEFAULT_TRAIN_SPLIT)
    p.add_argument("--text_field", type=str, default=DEFAULT_TEXT_FIELD)
    p.add_argument("--title_field", type=str, default=DEFAULT_TITLE_FIELD)
    p.add_argument("--max_length", type=int, default=DEFAULT_MAX_LENGTH)
    p.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--grad_accum", type=int, default=DEFAULT_GRAD_ACCUM)
    p.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    p.add_argument("--lr", type=float, default=DEFAULT_LR)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--num_train_examples", type=int, default=DEFAULT_NUM_TRAIN_EXAMPLES)
    p.add_argument("--max_steps", type=int, default=DEFAULT_MAX_STEPS)
    return p.parse_args()


def to_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join([str(x) for x in v])
    if isinstance(v, dict):
        return "\n".join([f"{k}: {v[k]}" for k in sorted(v.keys())])
    return str(v)


def build_messages(title: str, speech: str) -> List[Dict[str, str]]:
    system = {
        "role": "system",
        "content": "You are an assistant that writes speeches in the style of a public figure (Trump-style)."
    }
    if title:
        user = {"role": "user", "content": f"Write a Trump-style speech about: {title}"}
    else:
        user = {"role": "user", "content": "Write a Trump-style speech."}
    assistant = {"role": "assistant", "content": speech.strip()}
    return [system, user, assistant]


def main():
    args = parse_args()
    cache_dir = get_hf_cache_dir()

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    ds = load_dataset(args.dataset_id, args.dataset_config, split=args.train_split, cache_dir=cache_dir)

    if args.num_train_examples and args.num_train_examples < len(ds):
        ds = ds.shuffle(seed=args.seed).select(range(args.num_train_examples))

    tokenizer = load_tokenizer(args.model_id, cache_dir=cache_dir)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tok(example):
        speech = to_text(example.get(args.text_field, ""))
        title = to_text(example.get(args.title_field, "")) if args.title_field in example else ""

        full = tokenizer.apply_chat_template(
            build_messages(title, speech), tokenize=False, add_generation_prompt=False
        )

        prompt_only = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": "You are an assistant that writes speeches in the style of a public figure (Trump-style)."},
                {"role": "user", "content": (f"Write a Trump-style speech about: {title}" if title else "Write a Trump-style speech.")},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )

        prompt_tok = tokenizer(prompt_only, truncation=True, max_length=args.max_length, add_special_tokens=False)
        full_tok = tokenizer(full, truncation=True, max_length=args.max_length, padding="max_length", add_special_tokens=False)

        labels = full_tok["input_ids"].copy()
        prompt_len = min(len(prompt_tok["input_ids"]), args.max_length)
        for i in range(prompt_len):
            labels[i] = -100
        for i, m in enumerate(full_tok["attention_mask"]):
            if m == 0:
                labels[i] = -100

        full_tok["labels"] = labels
        return full_tok

    tokenized = ds.map(tok, remove_columns=ds.column_names)

    use_cuda = torch.cuda.is_available()
    if use_cuda and hasattr(torch.cuda, "is_bf16_supported") and torch.cuda.is_bf16_supported():
        dtype = torch.bfloat16
    else:
        dtype = torch.float16 if use_cuda else torch.float32

    model = AutoModelForCausalLM.from_pretrained(args.model_id, cache_dir=cache_dir, dtype=dtype)
    device = torch.device("cuda" if use_cuda else "cpu")
    model.to(device)
    model.train()

    def collate(batch):
        input_ids = torch.tensor([ex["input_ids"] for ex in batch], dtype=torch.long)
        attention_mask = torch.tensor([ex["attention_mask"] for ex in batch], dtype=torch.long)
        labels = torch.tensor([ex["labels"] for ex in batch], dtype=torch.long)
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}

    loader = DataLoader(tokenized, batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    opt.zero_grad(set_to_none=True)
    seen = 0
    opt_step = 0

    for _epoch in range(args.epochs):
        for batch in loader:
            seen += 1
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss
            (loss / args.grad_accum).backward()

            if seen % args.grad_accum == 0:
                opt.step()
                opt.zero_grad(set_to_none=True)
                opt_step += 1

                if opt_step % 10 == 0:
                    print(f"opt_step={opt_step} loss={loss.item():.4f}")

                if args.max_steps and opt_step >= args.max_steps:
                    break
        if args.max_steps and opt_step >= args.max_steps:
            break

    os.makedirs(args.output_dir, exist_ok=True)
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
