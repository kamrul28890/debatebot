#!/usr/bin/env python3
"""
Compatibility bootstrap for local setup.

Recommended modern workflow:
    python -m pip install -e .
    python -m pip install -e ".[rag,qwen,xtts]"

Legacy workflow (this script):
    python setup.py --rag --qwen --xtts
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


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
    return parser.parse_args()


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10+ is required.")
        return 1

    args = parse_args()

    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    if args.rag:
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-rag.txt"])
    if args.qwen:
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-qwen.txt"])
    if args.xtts:
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-xtts.txt"])
    if args.dev:
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"])

    ensure_keys_file()

    print("Setup complete.")
    print("Run: python scripts/doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

