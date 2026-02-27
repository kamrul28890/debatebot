#!/usr/bin/env python3
"""
Comprehensive environment diagnostics for Debate Night.

Examples:
  python scripts/doctor.py
  python scripts/doctor.py --rag --qwen --xtts
  python scripts/doctor.py --ci
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


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


def can_import(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_probe(code: str, timeout_sec: int = 45) -> tuple[bool, dict]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except Exception as exc:
        return False, {"error": f"probe execution failed: {exc}"}

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return False, {"error": detail or f"probe exited with code {completed.returncode}"}

    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return False, {"error": "probe produced no output"}

    try:
        payload = json.loads(lines[-1])
    except Exception:
        return False, {"error": f"invalid probe output: {lines[-1]}"}
    return True, payload


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
        ROOT / "scripts" / "build_local_mode.py",
        ROOT / "scripts" / "prepare_debate_cache.py",
        ROOT / "scripts" / "setup_selected_mode.py",
        ROOT / "keys_template.py",
    ]
    for path in required:
        if path.exists():
            report.ok(f"Found {path.relative_to(ROOT)}")
        else:
            report.error(f"Missing required path: {path.relative_to(ROOT)}")


def check_import_group(report: DoctorReport, modules: list[str], hint: str = "") -> None:
    for mod in modules:
        ok, detail = can_import(mod)
        if ok:
            report.ok(f"Import OK: {mod}")
        else:
            suffix = f" ({hint})" if hint else ""
            report.error(f"Import failed: {mod}{suffix} -> {detail}")


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

    for env_name in ("AZURE_TTS_VOICE_TRUMP", "AZURE_TTS_VOICE_BIDEN", "AZURE_TTS_VOICE_SISKIND"):
        if os.getenv(env_name):
            report.ok(f"Azure TTS override detected: {env_name}")


def check_persona_assets(report: DoctorReport, xtts_enabled: bool) -> None:
    personas = ["trump", "biden", "siskind"]
    for persona in personas:
        base = ROOT / "data" / f"raw_{persona}"
        ref = base / "ref.wav"
        idle = base / "idle.png"
        talking = base / "talking.png"
        listening = base / "listening.png"

        if ref.exists():
            report.ok(f"Voice reference present: {ref.relative_to(ROOT)}")
        else:
            if xtts_enabled:
                report.error(f"Missing ref.wav: {ref.relative_to(ROOT)}")
            else:
                report.warn(f"Missing ref.wav: {ref.relative_to(ROOT)}")

        for img in (idle, talking, listening):
            if not img.exists():
                report.warn(f"Missing avatar image: {img.relative_to(ROOT)}")


def check_crowd_sounds(report: DoctorReport) -> None:
    sounds = [
        "applause",
        "laugh",
        "boo",
        "buzzer",
        "ding",
        "fanfare",
        "crickets",
        "drumroll",
    ]
    exts = (".wav", ".ogg", ".oga", ".mp3")
    sound_dir = ROOT / "data" / "crowd_sounds"
    missing = []
    for stem in sounds:
        if not any((sound_dir / f"{stem}{ext}").exists() for ext in exts):
            missing.append(stem)
    if not missing:
        report.ok("Crowd sounds present")
        return
    report.warn("Missing crowd sounds: " + ", ".join(missing))


def check_rag_assets(report: DoctorReport) -> None:
    for persona in ("trump", "biden"):
        speech_file = ROOT / "data" / f"raw_{persona}" / "speeches.txt"
        if speech_file.exists():
            report.ok(f"RAG source present: {speech_file.relative_to(ROOT)}")
        else:
            report.warn(f"RAG source missing: {speech_file.relative_to(ROOT)}")


def check_qwen_assets(report: DoctorReport) -> None:
    hf_token = bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))

    for persona in ("trump", "biden"):
        adapter_dir = ROOT / "data" / "models" / f"qwen-2.5-0.5b-finetuned-{persona}"
        dataset = ROOT / "data" / f"{persona}_train.jsonl"
        if dataset.exists():
            report.ok(f"Qwen dataset present: {dataset.relative_to(ROOT)}")
        else:
            report.warn(f"Qwen dataset missing: {dataset.relative_to(ROOT)}")

        if not adapter_dir.exists():
            if hf_token:
                report.warn(f"Qwen adapter missing for {persona}, but HF token fallback is available")
            else:
                report.error(f"Qwen adapter missing for {persona}: {adapter_dir.relative_to(ROOT)}")
            continue

        required = ["adapter_config.json"]
        optional_weights = ["adapter_model.safetensors", "adapter_model.bin"]
        missing_required = [name for name in required if not (adapter_dir / name).exists()]
        has_weights = any((adapter_dir / name).exists() for name in optional_weights)

        if missing_required:
            report.error(
                f"Qwen adapter incomplete for {persona}; missing: {', '.join(missing_required)}"
            )
        elif not has_weights:
            report.error(
                f"Qwen adapter incomplete for {persona}; missing adapter weights (.safetensors/.bin)"
            )
        else:
            report.ok(f"Qwen adapter ready: {adapter_dir.relative_to(ROOT)}")


def check_deterministic_cache_script(report: DoctorReport) -> None:
    try:
        from src.cache.deterministic import CACHE_VERSION, script_path

        expected_version = CACHE_VERSION
        path = script_path(ROOT)
    except Exception:
        expected_version = "unknown"
        path = ROOT / "data" / "cache_sessions" / "deterministic_debate_v2.json"

    if not path.exists():
        report.warn(f"Deterministic cache script missing: {path.relative_to(ROOT)}")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.error(f"Deterministic cache script unreadable: {exc}")
        return

    script_version = payload.get("version", "unknown")
    trump_lines = len(payload.get("trump", []))
    biden_lines = len(payload.get("biden", []))
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
    if expected_version != "unknown" and script_version != expected_version:
        report.warn(
            f"Deterministic cache is stale ({script_version}); expected {expected_version}. "
            "Run scripts/prepare_debate_cache.py --force."
        )
    report.ok(
        f"Deterministic cache script ready ({script_version}) | turns: trump={trump_lines}, "
        f"biden={biden_lines} | sync fingerprint={fingerprint}"
    )


def check_xtts_cache(report: DoctorReport) -> None:
    cache_root = ROOT / "data" / "xtts_cache"
    for persona in ("trump", "biden", "siskind"):
        p = cache_root / persona
        count = len(list(p.glob("*.wav"))) if p.is_dir() else 0
        if count > 0:
            report.ok(f"XTTS cache ready for {persona}: {count} wav files")
        else:
            report.warn(f"XTTS cache empty for {persona}: {p.relative_to(ROOT)}")


def check_qwen_runtime(report: DoctorReport) -> None:
    code = (
        "import json\n"
        "payload={'ready': False, 'error': ''}\n"
        "try:\n"
        "    import torch\n"
        "    from PyQt6.QtWidgets import QApplication\n"
        "    import transformers\n"
        "    import peft\n"
        "    import src.brain.qwen_brain\n"
        "    payload['ready'] = True\n"
        "except Exception as exc:\n"
        "    payload['error'] = str(exc)\n"
        "print(json.dumps(payload))\n"
    )
    ok, payload = run_probe(code)
    if not ok:
        report.error(f"Qwen runtime probe failed: {payload.get('error', 'unknown error')}")
        return
    if payload.get("ready"):
        report.ok("Qwen runtime probe passed")
    else:
        report.error(f"Qwen runtime unavailable: {payload.get('error', 'unknown error')}")


def check_xtts_runtime(report: DoctorReport) -> None:
    code = (
        "import json\n"
        "payload={'ready': False, 'error': ''}\n"
        "try:\n"
        "    import torch\n"
        "    from PyQt6.QtWidgets import QApplication\n"
        "    from src.audio import xtts_speaker as m\n"
        "    payload['ready'] = bool(getattr(m, 'XTTS_AVAILABLE', False))\n"
        "    payload['error'] = str(getattr(m, 'XTTS_IMPORT_ERROR', '') or '')\n"
        "except Exception as exc:\n"
        "    payload['error'] = str(exc)\n"
        "print(json.dumps(payload))\n"
    )
    ok, payload = run_probe(code)
    if not ok:
        report.error(f"XTTS runtime probe failed: {payload.get('error', 'unknown error')}")
        return
    if payload.get("ready"):
        report.ok("XTTS runtime probe passed")
    else:
        detail = payload.get("error", "") or "XTTS runtime unavailable"
        report.error(f"XTTS runtime unavailable: {detail}")


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
    check_credentials(report, ci_mode=args.ci)
    check_persona_assets(report, xtts_enabled=args.xtts)
    check_crowd_sounds(report)
    check_deterministic_cache_script(report)

    core_imports = [
        "openai",
        "azure.cognitiveservices.speech",
        "PyQt6",
        "requests",
        "bs4",
        "pygame",
    ]
    check_import_group(report, core_imports)

    if args.rag:
        check_import_group(report, ["numpy", "sentence_transformers"], hint="install requirements-rag.txt")
        check_rag_assets(report)

    if args.qwen:
        check_import_group(
            report,
            ["torch", "transformers", "peft", "datasets", "accelerate", "huggingface_hub"],
            hint="install requirements-qwen.txt",
        )
        check_qwen_runtime(report)
        check_qwen_assets(report)

    if args.xtts:
        check_import_group(
            report,
            ["numpy", "TTS", "torchaudio", "soundfile"],
            hint="install requirements-xtts.txt",
        )
        check_xtts_runtime(report)
        check_xtts_cache(report)

    print("")
    print(f"Summary: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
