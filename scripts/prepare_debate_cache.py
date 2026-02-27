#!/usr/bin/env python3
"""
Prepare deterministic cached assets for one debate module.

This script is designed to run from the GUI task runner and emits progress lines:
    PROGRESS:<percent>:<message>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cache.deterministic import ensure_script, script_path


def progress(percent: int, message: str) -> None:
    value = max(0, min(100, int(percent)))
    print(f"PROGRESS:{value}:{message}", flush=True)
    print(message, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare cached debate assets.")
    parser.add_argument("--persona", choices=["trump", "biden"], required=True)
    parser.add_argument("--voice", choices=["azure", "xtts"], required=True)
    parser.add_argument("--force", action="store_true", help="Rebuild deterministic script and refresh assets.")
    return parser.parse_args()


def _prepare_xtts(persona: str, script: dict) -> None:
    progress(30, "Checking XTTS runtime")
    from src.audio.xtts_speaker import XTTS_AVAILABLE, XTTS_IMPORT_ERROR, XTTSSpeaker

    if not XTTS_AVAILABLE:
        detail = XTTS_IMPORT_ERROR or "unknown XTTS import error"
        raise RuntimeError(f"XTTS runtime is unavailable: {detail}")

    persona_lines = list(script.get(persona, []))
    siskind_lines = list(script.get("siskind", []))
    total = len(persona_lines) + len(siskind_lines)
    done_so_far = 0

    progress(38, f"Loading XTTS speaker for {persona}")
    persona_speaker = XTTSSpeaker(persona)
    if not persona_speaker._ready:
        raise RuntimeError(f"XTTS speaker is not ready for {persona} (check ref.wav and runtime)")

    progress(48, f"Caching {persona} responses ({len(persona_lines)} lines)")

    def _persona_cb(index: int, _total: int, text: str, _done: int, _skipped: int) -> None:
        pct = 48 + int((index / max(total, 1)) * 32)
        preview = " ".join(text.split())[:52]
        progress(pct, f"{persona} cache {index}/{len(persona_lines)}: {preview}")

    persona_speaker.pregenerate(
        persona_lines,
        show_progress=False,
        progress_callback=_persona_cb,
    )
    done_so_far += len(persona_lines)

    progress(82, "Loading XTTS speaker for siskind")
    siskind_speaker = XTTSSpeaker("siskind")
    if not siskind_speaker._ready:
        raise RuntimeError("XTTS speaker is not ready for siskind (check data/raw_siskind/ref.wav)")

    progress(86, f"Caching siskind responses ({len(siskind_lines)} lines)")

    def _siskind_cb(index: int, _total: int, text: str, _done: int, _skipped: int) -> None:
        current = done_so_far + index
        pct = 86 + int((current / max(total, 1)) * 12)
        preview = " ".join(text.split())[:52]
        progress(pct, f"siskind cache {index}/{len(siskind_lines)}: {preview}")

    siskind_speaker.pregenerate(
        siskind_lines,
        show_progress=False,
        progress_callback=_siskind_cb,
    )


def _write_manifest(persona: str, voice: str, script: dict) -> Path:
    cache_dir = ROOT / "data" / "cache_sessions"
    cache_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "cache_kind": "module_cached_mode",
        "persona": persona,
        "voice": voice,
        "script_version": script.get("version", "unknown"),
        "script_path": str(script_path(ROOT).relative_to(ROOT)).replace("\\", "/"),
        "persona_turns": len(script.get(persona, [])),
        "siskind_turns": len(script.get("siskind", [])),
    }
    manifest_path = cache_dir / f"prepared_{persona}_{voice}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    args = parse_args()

    progress(5, "Preparing deterministic debate script")
    script = ensure_script(ROOT, force_rebuild=args.force)
    progress(20, f"Deterministic script ready: {script.get('version', 'unknown')}")

    if args.voice == "xtts":
        _prepare_xtts(args.persona, script)
    else:
        progress(70, "Azure voice selected: no local audio pre-generation required")

    manifest = _write_manifest(args.persona, args.voice, script)
    progress(100, f"Cache preparation complete: {manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

