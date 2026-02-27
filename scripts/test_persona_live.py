#!/usr/bin/env python3
"""
Simple one-machine live loop for debugging STT -> brain -> voice.

Usage:
  python scripts/test_persona_live.py --persona biden --brain azure --voice azure
"""

from __future__ import annotations

import argparse
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.audio.listener import DebateListener
from src.audio.xtts_speaker import DualSpeaker
from src.brain.model import DebateBrain
from src.utils.logging_utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-machine persona loop test.")
    parser.add_argument("--persona", choices=["trump", "biden"], default="biden")
    parser.add_argument("--brain", choices=["azure", "qwen"], default="azure")
    parser.add_argument("--voice", choices=["azure", "xtts"], default="azure")
    parser.add_argument("--turns", type=int, default=3, help="How many listen/respond turns to run.")
    parser.add_argument("--timeout", type=int, default=45, help="Listen timeout per turn (seconds).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging()

    print(
        f"[TEST] persona={args.persona} brain={args.brain} voice={args.voice} "
        f"turns={args.turns} timeout={args.timeout}s",
        flush=True,
    )
    print("[TEST] Speak naturally after each prompt. Ctrl+C to stop.\n", flush=True)

    brain = DebateBrain(args.persona, brain_type=args.brain)
    speaker = DualSpeaker(args.persona, mode=args.voice)
    listener = DebateListener()
    speech_words_per_second = 2.1

    try:
        for idx in range(1, max(1, args.turns) + 1):
            print(f"[TURN {idx}] Listening...", flush=True)
            heard = listener.listen_for_turn(timeout_seconds=max(5, args.timeout))
            if not heard:
                print(f"[TURN {idx}] No speech recognized.", flush=True)
                continue

            print(f"[TURN {idx}] Heard: {heard}", flush=True)
            reply = brain.generate_response(heard)
            print(f"[TURN {idx}] Reply: {reply}", flush=True)

            words = len(reply.split())
            listener.mute_for(words / speech_words_per_second + 1.5)
            speaker.speak(reply)

    except KeyboardInterrupt:
        print("\n[TEST] Stopped by user.", flush=True)
    finally:
        try:
            listener.stop()
        except Exception:
            pass
        try:
            speaker.stop()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
