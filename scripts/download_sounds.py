#!/usr/bin/env python3
"""
Download crowd sound effects automatically for Debate Night.

Primary source: Wikimedia Commons audio files.
Behavior:
- Downloads files into data/crowd_sounds/
- Preserves source extension (.wav/.ogg)
- Writes attribution metadata to data/crowd_sounds/SOURCES.json
- Falls back to generated synthetic WAV clips when download fails

Usage:
    python scripts/download_sounds.py
    python scripts/download_sounds.py --force
    python scripts/download_sounds.py --no-fallback
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOUNDS_DIR = ROOT / "data" / "crowd_sounds"
ATTRIBUTION_FILE = SOUNDS_DIR / "SOURCES.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "debate-night-sound-fetcher/1.0"

# Curated set chosen for coverage + reliability.
# All items are public media hosted on Wikimedia Commons.
SOUND_LIBRARY: dict[str, dict[str, str]] = {
    "applause": {
        "title": "File:Applause-2.ogg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/5/5b/Applause-2.ogg",
        "description": "Crowd applause",
    },
    "laugh": {
        "title": "File:High pitched Laughter.wav",
        "url": "https://upload.wikimedia.org/wikipedia/commons/0/01/High_pitched_Laughter.wav",
        "description": "Audience laughter",
    },
    "boo": {
        "title": "File:Soundgoats - Audience Booing.wav",
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/e5/Soundgoats_-_Audience_Booing.wav",
        "description": "Crowd booing",
    },
    "buzzer": {
        "title": "File:Buzzer.wav",
        "url": "https://upload.wikimedia.org/wikipedia/commons/5/55/Buzzer.wav",
        "description": "Wrong-answer buzzer",
    },
    "ding": {
        "title": "File:Ding Dong Bicycle Bell A.ogg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/f/f7/Ding_Dong_Bicycle_Bell_A.ogg",
        "description": "Correct-answer ding",
    },
    "fanfare": {
        "title": "File:Kevin MacLeod - Fanfare for Space.ogg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/f/f7/Kevin_MacLeod_-_Fanfare_for_Space.ogg",
        "description": "Fanfare",
    },
    "crickets": {
        "title": "File:Crickets choir.ogg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/4c/Crickets_choir.ogg",
        "description": "Crickets / awkward silence",
    },
    "drumroll": {
        "title": "File:Drum Roll Intro.ogg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/c4/Drum_Roll_Intro.ogg",
        "description": "Drum roll",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download crowd sounds for Debate Night.")
    parser.add_argument("--force", action="store_true", help="Redownload even if a local file exists.")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not generate synthetic fallback sounds when download fails.",
    )
    return parser.parse_args()


def commons_file_url(file_title: str) -> str:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "url",
        }
    )
    req = urllib.request.Request(
        f"{COMMONS_API}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        return ""
    page = next(iter(pages.values()))
    infos = page.get("imageinfo", [])
    if not infos:
        return ""
    return infos[0].get("url", "")


def detect_existing(sound_key: str) -> Path | None:
    for ext in (".wav", ".ogg", ".oga", ".mp3"):
        path = SOUNDS_DIR / f"{sound_key}{ext}"
        if path.exists():
            return path
    return None


def target_path(sound_key: str, source_url: str) -> Path:
    ext = Path(urllib.parse.urlparse(source_url).path).suffix.lower()
    if ext not in (".wav", ".ogg", ".oga", ".mp3"):
        ext = ".wav"
    return SOUNDS_DIR / f"{sound_key}{ext}"


def download_file(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()
    dst.write_bytes(data)


def _clamp_i16(x: float) -> int:
    v = int(max(-1.0, min(1.0, x)) * 32767)
    return max(-32768, min(32767, v))


def _render_tone(
    path: Path,
    duration_s: float,
    freq_hz: float = 440.0,
    volume: float = 0.35,
    sweep_to_hz: float | None = None,
) -> None:
    rate = 44100
    n = int(duration_s * rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            t = i / rate
            if sweep_to_hz is None:
                f = freq_hz
            else:
                f = freq_hz + (sweep_to_hz - freq_hz) * (i / max(1, n - 1))
            sample = volume * math.sin(2.0 * math.pi * f * t)
            frames += struct.pack("<h", _clamp_i16(sample))
        wav.writeframes(bytes(frames))


def _render_noise_bursts(path: Path, duration_s: float, burst_count: int, seed: int) -> None:
    import random

    rng = random.Random(seed)
    rate = 44100
    n = int(duration_s * rate)
    burst_centers = [rng.randint(0, n - 1) for _ in range(burst_count)]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            env = 0.0
            for c in burst_centers:
                d = abs(i - c) / rate
                env += math.exp(-((d * 18.0) ** 2))
            env = min(env, 1.0)
            noise = rng.uniform(-1.0, 1.0) * env * 0.32
            frames += struct.pack("<h", _clamp_i16(noise))
        wav.writeframes(bytes(frames))


def generate_fallback_wav(sound_key: str, dst: Path) -> None:
    dst = dst.with_suffix(".wav")
    if sound_key == "ding":
        _render_tone(dst, duration_s=0.28, freq_hz=1046.5, volume=0.35)
    elif sound_key == "buzzer":
        _render_tone(dst, duration_s=0.55, freq_hz=220.0, sweep_to_hz=140.0, volume=0.38)
    elif sound_key == "fanfare":
        # short rising tone as minimal fanfare fallback
        _render_tone(dst, duration_s=1.0, freq_hz=440.0, sweep_to_hz=660.0, volume=0.30)
    elif sound_key == "drumroll":
        _render_noise_bursts(dst, duration_s=1.1, burst_count=26, seed=31)
    elif sound_key == "crickets":
        _render_noise_bursts(dst, duration_s=1.2, burst_count=18, seed=73)
    elif sound_key == "applause":
        _render_noise_bursts(dst, duration_s=1.2, burst_count=35, seed=11)
    elif sound_key == "laugh":
        _render_noise_bursts(dst, duration_s=1.0, burst_count=24, seed=19)
    elif sound_key == "boo":
        _render_tone(dst, duration_s=0.9, freq_hz=160.0, sweep_to_hz=120.0, volume=0.34)
    else:
        _render_tone(dst, duration_s=0.4, freq_hz=440.0, volume=0.25)


def main() -> int:
    args = parse_args()
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    attributions: dict[str, dict[str, str]] = {}
    failures: list[str] = []

    print(f"Downloading crowd sounds into: {SOUNDS_DIR}")
    for key, meta in SOUND_LIBRARY.items():
        existing = detect_existing(key)
        if existing and not args.force:
            print(f"  [skip] {key}: already present ({existing.name})")
            attributions[key] = {
                "source": "local",
                "file": existing.name,
                "description": meta["description"],
            }
            continue

        file_title = meta["title"]
        try:
            url = meta.get("url", "") or commons_file_url(file_title)
            if not url:
                raise RuntimeError("no downloadable URL returned by Commons API")

            dst = target_path(key, url)
            # remove any existing alternative extension so only one canonical file remains
            for ext in (".wav", ".ogg", ".oga", ".mp3"):
                alt = SOUNDS_DIR / f"{key}{ext}"
                if alt.exists() and alt != dst:
                    alt.unlink()

            download_file(url, dst)
            print(f"  [ok]   {key}: downloaded {dst.name}")
            attributions[key] = {
                "source": "wikimedia_commons",
                "title": file_title,
                "url": url,
                "file": dst.name,
                "description": meta["description"],
            }
        except Exception as exc:
            failures.append(f"{key} ({exc})")
            if args.no_fallback:
                print(f"  [fail] {key}: {exc}")
                continue
            fallback_path = SOUNDS_DIR / f"{key}.wav"
            try:
                generate_fallback_wav(key, fallback_path)
                print(f"  [fallback] {key}: generated {fallback_path.name}")
                attributions[key] = {
                    "source": "generated_fallback",
                    "file": fallback_path.name,
                    "description": meta["description"],
                }
            except Exception as gen_exc:
                failures.append(f"{key} fallback ({gen_exc})")
                print(f"  [fail] {key}: download and fallback both failed ({gen_exc})")

    ATTRIBUTION_FILE.write_text(json.dumps(attributions, indent=2), encoding="utf-8")
    print(f"\nWrote attribution metadata: {ATTRIBUTION_FILE}")

    missing = [k for k in SOUND_LIBRARY if detect_existing(k) is None]
    if missing:
        print("\nMissing sounds after download:", ", ".join(missing))
        return 1

    if failures:
        print("\nCompleted with fallback usage/errors:")
        for item in failures:
            print(f"  - {item}")
    else:
        print("\nAll sounds downloaded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
