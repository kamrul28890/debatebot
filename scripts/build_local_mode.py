#!/usr/bin/env python3
"""Build fully local/cached assets for Debate Night modes.

The build can target:
- one persona: trump or biden
- all personas: trump + biden (+ siskind voice cache)

Pipeline:
1) optional dependency install/repair
2) optional Qwen fine-tuning
3) optional XTTS cache generation
4) doctor validation
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list[str]) -> int:
    print(f"\n=== {name} ===")
    print("$ " + " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(ROOT))
    if completed.returncode == 0:
        print(f"[OK] {name} completed")
    else:
        print(f"[ERROR] {name} failed with exit code {completed.returncode}")
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local/cached Debate Night assets.")
    parser.add_argument(
        "--persona",
        choices=["trump", "biden", "all"],
        default="all",
        help="Target persona(s).",
    )
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation.")
    parser.add_argument("--skip-train", action="store_true", help="Skip Qwen fine-tuning.")
    parser.add_argument("--skip-cache", action="store_true", help="Skip XTTS cache generation.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure.")
    return parser.parse_args()


def personas_for_qwen(persona_flag: str) -> list[str]:
    if persona_flag == "all":
        return ["trump", "biden"]
    return [persona_flag]


def personas_for_xtts_cache(persona_flag: str) -> list[str]:
    if persona_flag == "all":
        return ["trump", "biden"]
    return [persona_flag]


def main() -> int:
    args = parse_args()
    py = sys.executable
    failures = 0

    qwen_personas = personas_for_qwen(args.persona)
    cache_personas = personas_for_xtts_cache(args.persona)

    if not args.skip_install:
        rc = run_step(
            "Install/repair Qwen + XTTS dependencies",
            [py, "scripts/bootstrap.py", "--qwen", "--xtts", "--doctor"],
        )
        if rc != 0:
            failures += 1
            if args.fail_fast:
                return rc

    if not args.skip_train:
        for persona in qwen_personas:
            adapter_dir = ROOT / "data" / "models" / f"qwen-2.5-0.5b-finetuned-{persona}"
            dataset = ROOT / "data" / f"{persona}_train.jsonl"

            if adapter_dir.exists():
                print(f"[SKIP] Local Qwen adapter already exists: {adapter_dir}")
                continue
            if not dataset.exists():
                print(f"[WARN] Dataset missing, skipping Qwen training for {persona}: {dataset}")
                continue

            rc = run_step(
                f"Train Qwen ({persona})",
                [py, "scripts/finetune_qwen.py", "--persona", persona],
            )
            if rc != 0:
                failures += 1
                if args.fail_fast:
                    return rc

    if not args.skip_cache:
        for persona in cache_personas:
            ref_selected = ROOT / "data" / f"raw_{persona}" / "ref.wav"
            ref_siskind = ROOT / "data" / "raw_siskind" / "ref.wav"
            if not ref_selected.exists():
                print(f"[WARN] ref.wav missing, skipping XTTS cache for {persona}: {ref_selected}")
                continue
            if not ref_siskind.exists():
                print(f"[WARN] ref.wav missing, skipping XTTS cache for siskind: {ref_siskind}")
                continue

            rc = run_step(
                f"Prepare deterministic cached mode ({persona} + siskind XTTS)",
                [py, "scripts/prepare_debate_cache.py", "--persona", persona, "--voice", "xtts"],
            )
            if rc != 0:
                failures += 1
                if args.fail_fast:
                    return rc

    rc = run_step("Doctor validation", [py, "scripts/doctor.py", "--qwen", "--xtts"])
    if rc != 0:
        failures += 1

    print("\n=== Summary ===")
    if failures:
        print(f"Build finished with {failures} failing step(s).")
        return 1

    print("Build finished successfully. All requested local/cached assets are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
