#!/usr/bin/env python3
"""
Project preflight diagnostics.

Examples:
  python scripts/doctor.py
  python scripts/doctor.py --rag --qwen --xtts
  python scripts/doctor.py --ci
"""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DoctorReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"[ERROR] {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"[WARN]  {msg}")

    def ok(self, msg: str) -> None:
        print(f"[OK]    {msg}")


def can_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def check_python(report: DoctorReport) -> None:
    if sys.version_info < (3, 10):
        report.error(f"Python {sys.version.split()[0]} detected; requires >=3.10")
    else:
        report.ok(f"Python {sys.version.split()[0]}")


def check_paths(report: DoctorReport) -> None:
    required = [
        ROOT / "src" / "main.py",
        ROOT / "src" / "brain" / "model.py",
        ROOT / "scripts" / "finetune_qwen.py",
        ROOT / "keys_template.py",
    ]
    for path in required:
        if path.exists():
            report.ok(f"Found {path.relative_to(ROOT)}")
        else:
            report.error(f"Missing required path: {path.relative_to(ROOT)}")


def check_imports(report: DoctorReport, rag: bool, qwen: bool, xtts: bool) -> None:
    core = [
        "openai",
        "azure.cognitiveservices.speech",
        "PyQt6",
        "requests",
        "bs4",
        "pygame",
    ]
    for mod in core:
        if can_import(mod):
            report.ok(f"Import OK: {mod}")
        else:
            report.error(f"Import failed: {mod}")

    if rag:
        for mod in ["numpy", "sentence_transformers"]:
            if can_import(mod):
                report.ok(f"Import OK: {mod}")
            else:
                report.error(f"Import failed: {mod} (install requirements-rag.txt)")

    if qwen:
        for mod in ["torch", "transformers", "peft", "datasets", "accelerate", "huggingface_hub"]:
            if can_import(mod):
                report.ok(f"Import OK: {mod}")
            else:
                report.error(f"Import failed: {mod} (install requirements-qwen.txt)")

    if xtts:
        for mod in ["numpy", "TTS", "torchaudio", "soundfile"]:
            if can_import(mod):
                report.ok(f"Import OK: {mod}")
            else:
                report.error(f"Import failed: {mod} (install requirements-xtts.txt)")


def check_credentials(report: DoctorReport, ci_mode: bool) -> None:
    if ci_mode:
        report.ok("CI mode: credential checks skipped")
        return

    env_keys = [
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
    ]
    env_present = all(os.getenv(k) for k in env_keys)
    if env_present:
        report.ok("Azure credentials found in environment variables")
        return

    keys_file = ROOT / "keys.py"
    if not keys_file.exists():
        report.warn("No env credentials and keys.py is missing")
        return

    try:
        raw = keys_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        report.warn(f"Could not read keys.py: {exc}")
        return

    if "YOUR_AZURE" in raw or '""' in raw:
        report.warn("keys.py exists but appears to contain placeholder values")
    else:
        report.ok("keys.py exists (local credential source)")


def check_assets(report: DoctorReport, xtts: bool) -> None:
    personas = ["trump", "biden", "siskind"]
    for persona in personas:
        ref = ROOT / "data" / f"raw_{persona}" / "ref.wav"
        if ref.exists():
            report.ok(f"Voice reference present: data/raw_{persona}/ref.wav")
        else:
            if xtts:
                report.error(f"Missing ref.wav for {persona}: {ref.relative_to(ROOT)}")
            else:
                report.warn(f"Missing ref.wav for {persona}: {ref.relative_to(ROOT)}")


def check_qwen_paths(report: DoctorReport, qwen: bool) -> None:
    if not qwen:
        return
    local_trump = ROOT / "data" / "models" / "qwen-2.5-0.5b-finetuned-trump"
    local_biden = ROOT / "data" / "models" / "qwen-2.5-0.5b-finetuned-biden"
    has_local = local_trump.exists() and local_biden.exists()
    has_hf_token = bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))

    if has_local:
        report.ok("Local Qwen adapters found for trump and biden")
    elif has_hf_token:
        report.warn("No local Qwen adapters found; HF token present for hub fallback")
    else:
        report.warn("No local Qwen adapters and no HF token found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Debate Night environment diagnostics.")
    parser.add_argument("--rag", action="store_true", help="Validate optional RAG stack.")
    parser.add_argument("--qwen", action="store_true", help="Validate optional Qwen stack.")
    parser.add_argument("--xtts", action="store_true", help="Validate optional XTTS stack.")
    parser.add_argument("--ci", action="store_true", help="CI mode (skip credential checks).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Debate Night Doctor | OS={platform.system()} | cwd={ROOT}")
    report = DoctorReport()

    check_python(report)
    check_paths(report)
    check_imports(report, rag=args.rag, qwen=args.qwen, xtts=args.xtts)
    check_credentials(report, ci_mode=args.ci)
    check_assets(report, xtts=args.xtts)
    check_qwen_paths(report, qwen=args.qwen)

    print("")
    print(f"Summary: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
