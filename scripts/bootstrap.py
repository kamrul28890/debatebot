#!/usr/bin/env python3
"""Cross-platform bootstrap installer for Debate Night.

Examples:
  python scripts/bootstrap.py
  python scripts/bootstrap.py --rag --qwen --xtts
  python scripts/bootstrap.py --rag --qwen --xtts --dev --doctor
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def ensure_keys_file() -> None:
    template = ROOT / "keys_template.py"
    keys = ROOT / "keys.py"
    if keys.exists():
        print("keys.py already exists.")
        return
    if template.exists():
        shutil.copy(template, keys)
        print("Created keys.py from keys_template.py.")
        print("Edit keys.py with valid credentials before runtime.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Debate Night dependencies.")
    parser.add_argument("--rag", action="store_true", help="Install RAG dependencies.")
    parser.add_argument("--qwen", action="store_true", help="Install Qwen dependencies.")
    parser.add_argument("--xtts", action="store_true", help="Install XTTS dependencies.")
    parser.add_argument("--dev", action="store_true", help="Install dev/test dependencies.")
    parser.add_argument("--doctor", action="store_true", help="Run scripts/doctor.py after installation.")
    parser.add_argument("--no-editable", action="store_true", help="Install as a regular package instead of editable.")
    return parser.parse_args()


def build_install_target(args: argparse.Namespace) -> tuple[list[str], str]:
    extras: list[str] = []
    if args.rag:
        extras.append("rag")
    if args.qwen:
        extras.append("qwen")
    if args.xtts:
        extras.append("xtts")
    if args.dev:
        extras.append("dev")

    suffix = ""
    if extras:
        suffix = f"[{','.join(extras)}]"

    target = f".{suffix}"
    pip_args = [target] if args.no_editable else ["-e", target]
    return pip_args, target


def run_doctor(args: argparse.Namespace) -> None:
    cmd = [sys.executable, "scripts/doctor.py"]
    if args.rag:
        cmd.append("--rag")
    if args.qwen:
        cmd.append("--qwen")
    if args.xtts:
        cmd.append("--xtts")
    run(cmd)


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10+ is required.")
        return 1

    args = parse_args()
    install_args, install_target = build_install_target(args)

    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", *install_args])
    run([sys.executable, "-m", "pip", "check"])

    ensure_keys_file()

    if args.doctor:
        run_doctor(args)

    print("Setup complete.")
    print(f"Installed target: {install_target}")
    print("Run: python scripts/doctor.py --rag --qwen --xtts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
