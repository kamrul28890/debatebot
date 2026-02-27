#!/usr/bin/env python3
"""One-click setup pipeline for a selected debate module/persona.

Designed for first-time teammates and GUI background execution.
Prints progress lines in this format:
    PROGRESS:<percent>:<message>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


COMBOS = {
    "azure_robotic": {"brain": "azure", "voice": "azure", "label": "Azure + Robotic Voice"},
    "qwen_robotic": {"brain": "qwen", "voice": "azure", "label": "Qwen + Robotic Voice"},
    "azure_cloned": {"brain": "azure", "voice": "xtts", "label": "Azure + Cloned Voice"},
    "qwen_cloned": {"brain": "qwen", "voice": "xtts", "label": "Qwen + Cloned Voice"},
}


def emit_progress(percent: int, message: str) -> None:
    value = max(0, min(100, int(percent)))
    print(f"PROGRESS:{value}:{message}", flush=True)
    print(message, flush=True)


def run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===", flush=True)
    print("$ " + " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(ROOT))
    if completed.returncode == 0:
        print(f"[OK] {name}", flush=True)
    else:
        print(f"[ERROR] {name} failed with exit code {completed.returncode}", flush=True)
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up a selected debate module end-to-end.")
    parser.add_argument("--persona", choices=["trump", "biden"], required=True)
    parser.add_argument("--combo", choices=sorted(COMBOS.keys()), required=True)
    parser.add_argument("--with-rag", action="store_true", help="Install/validate optional RAG stack.")
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation.")
    parser.add_argument("--skip-train", action="store_true", help="Skip Qwen fine-tuning when local adapter missing.")
    parser.add_argument("--skip-cache", action="store_true", help="Skip deterministic/XTTS cache preparation.")
    parser.add_argument("--force-cache", action="store_true", help="Force deterministic cache rebuild.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately on first failed step.")
    return parser.parse_args()


def has_hf_fallback() -> bool:
    return bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))


def require_xtts_refs(persona: str) -> list[str]:
    missing = []
    for p in (persona, "siskind"):
        ref = ROOT / "data" / f"raw_{p}" / "ref.wav"
        if not ref.exists():
            missing.append(str(ref.relative_to(ROOT)))
    return missing


def ensure_qwen_adapter(persona: str, skip_train: bool, fail_fast: bool) -> int:
    adapter_dir = ROOT / "data" / "models" / f"qwen-2.5-0.5b-finetuned-{persona}"
    if adapter_dir.exists():
        emit_progress(52, f"Qwen adapter already present for {persona}")
        return 0

    if has_hf_fallback():
        emit_progress(52, f"No local Qwen adapter for {persona}; HF token fallback detected")
        return 0

    dataset = ROOT / "data" / f"{persona}_train.jsonl"
    if not dataset.exists():
        print(f"[ERROR] Missing dataset required for Qwen training: {dataset.relative_to(ROOT)}", flush=True)
        return 2

    if skip_train:
        print(
            "[ERROR] Qwen adapter is missing and --skip-train was requested. "
            "Cannot complete setup for a Qwen module.",
            flush=True,
        )
        return 3

    emit_progress(56, f"Training Qwen adapter for {persona} (first run can take time)")
    rc = run_step("Train Qwen adapter", [PY, "scripts/finetune_qwen.py", "--persona", persona])
    if rc != 0 and fail_fast:
        return rc
    return rc


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10+ is required.", flush=True)
        return 1

    args = parse_args()
    combo = COMBOS[args.combo]
    need_qwen = combo["brain"] == "qwen"
    need_xtts = combo["voice"] == "xtts"

    emit_progress(3, f"Setup starting for {combo['label']} [{args.persona}]")
    emit_progress(8, "Running preflight checks")

    if need_xtts:
        missing_refs = require_xtts_refs(args.persona)
        if missing_refs:
            print("[ERROR] XTTS reference audio is missing:", flush=True)
            for rel in missing_refs:
                print(f"  - {rel}", flush=True)
            return 4

    emit_progress(12, "Preflight checks passed")

    failures = 0

    if not args.skip_install:
        install_cmd = [PY, "scripts/bootstrap.py"]
        if need_qwen:
            install_cmd.append("--qwen")
        if need_xtts:
            install_cmd.append("--xtts")
        if args.with_rag:
            install_cmd.append("--rag")

        emit_progress(18, "Installing required dependencies")
        rc = run_step("Install dependencies", install_cmd)
        if rc != 0:
            failures += 1
            if args.fail_fast:
                return rc

    if need_qwen:
        rc = ensure_qwen_adapter(
            persona=args.persona,
            skip_train=args.skip_train,
            fail_fast=args.fail_fast,
        )
        if rc != 0:
            failures += 1
            if args.fail_fast:
                return rc
    else:
        emit_progress(52, "Qwen setup skipped (Azure brain module)")

    if not args.skip_cache:
        emit_progress(68, "Preparing deterministic cache profile")
        cache_cmd = [
            PY,
            "scripts/prepare_debate_cache.py",
            "--persona",
            args.persona,
            "--voice",
            combo["voice"],
        ]
        if args.force_cache:
            cache_cmd.append("--force")
        rc = run_step("Prepare module cache", cache_cmd)
        if rc != 0:
            failures += 1
            if args.fail_fast:
                return rc
    else:
        emit_progress(68, "Cache preparation skipped by request")

    emit_progress(86, "Running doctor validation for selected module")
    doctor_cmd = [PY, "scripts/doctor.py"]
    if need_qwen:
        doctor_cmd.append("--qwen")
    if need_xtts:
        doctor_cmd.append("--xtts")
    if args.with_rag:
        doctor_cmd.append("--rag")
    rc = run_step("Doctor validation", doctor_cmd)
    if rc != 0:
        failures += 1
        if args.fail_fast:
            return rc

    if failures:
        emit_progress(100, f"Setup finished with {failures} failing step(s)")
        return 1

    emit_progress(100, "Setup complete. Selected module is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

