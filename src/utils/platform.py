"""
src/utils/platform.py

Cross-platform compatibility layer.
Import this instead of calling platform.system() or sys.platform scattered around.

Handles:
- Audio playback (WAV files)
- Environment variable reading
- Font availability
- Path helpers
- Console colors

Works on: macOS, Windows 10/11, Linux
"""

import os
import sys
import platform

# ── OS detection ──────────────────────────────────────────────────────────────
SYSTEM = platform.system()   # "Darwin", "Windows", "Linux"
IS_MAC     = SYSTEM == "Darwin"
IS_WINDOWS = SYSTEM == "Windows"
IS_LINUX   = SYSTEM == "Linux"


# ── Environment variables ──────────────────────────────────────────────────────
def get_env(key: str, default: str = "") -> str:
    """
    Read an environment variable cross-platform.
    
    Mac/Linux:  PERSONA=trump python src/main.py
    Windows:    set PERSONA=trump && python src/main.py
                OR: $env:PERSONA="trump"; python src/main.py  (PowerShell)
    """
    return os.environ.get(key, default)


# ── WAV audio playback ────────────────────────────────────────────────────────
def play_wav_blocking(path: str) -> bool:
    """
    Play a WAV file and block until it finishes.
    Uses pygame (cross-platform) with OS-specific fallbacks.
    Returns True on success.
    """
    if not os.path.exists(path):
        print(f"[Audio] File not found: {path}")
        return False

    # ── Primary on Windows: winsound (usually more reliable for default device)
    if IS_WINDOWS:
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return True
        except Exception as e:
            print(f"[Audio] winsound failed ({e}), trying pygame...")

    # ── Primary (cross-platform): pygame ───────────────────────────────────────
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        sound = pygame.mixer.Sound(path)
        channel = sound.play()
        if channel is None:
            print("[Audio] pygame returned no playback channel, trying OS fallback...")
            raise RuntimeError("pygame channel unavailable")
        import time
        while channel and channel.get_busy():
            time.sleep(0.05)
        return True
    except Exception as e:
        print(f"[Audio] pygame failed ({e}), trying OS fallback...")

    # ── Fallback per OS ────────────────────────────────────────────────────────
    try:
        import subprocess
        if IS_MAC:
            subprocess.run(["afplay", path], check=True, timeout=60)
            return True
        elif IS_WINDOWS:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return True
        elif IS_LINUX:
            # Try aplay, then paplay
            for player in ["aplay", "paplay", "ffplay"]:
                result = subprocess.run(
                    [player, path],
                    capture_output=True, timeout=60
                )
                if result.returncode == 0:
                    return True
    except Exception as e:
        print(f"[Audio] OS fallback failed: {e}")

    return False


def play_wav_nonblocking(path: str):
    """Play a WAV file without blocking. Returns immediately."""
    import threading
    t = threading.Thread(target=play_wav_blocking, args=(path,), daemon=True)
    t.start()
    return t


# ── Font resolution ────────────────────────────────────────────────────────────
# Returns font families that are available on the current OS.
# GUI code should call these instead of hardcoding font names.

def impact_font() -> str:
    """Bold display font — Impact on Windows, system equivalent on Mac."""
    if IS_WINDOWS:
        return "Impact"
    elif IS_MAC:
        return "Impact"          # Impact ships with macOS too
    else:
        return "Impact, 'Arial Black', sans-serif"


def monospace_font() -> str:
    if IS_WINDOWS:
        return "Consolas"
    elif IS_MAC:
        return "Menlo"
    else:
        return "DejaVu Sans Mono"


def serif_font() -> str:
    if IS_WINDOWS:
        return "Georgia"
    else:
        return "Georgia"


def comic_font() -> str:
    """The South Park paper-cutout vibe font."""
    if IS_WINDOWS:
        return "Comic Sans MS"
    elif IS_MAC:
        return "Chalkboard SE"
    else:
        return "Comic Sans MS, URW Chancery L"


# ── Console ────────────────────────────────────────────────────────────────────
def enable_windows_console_colors():
    """Enable ANSI color codes in Windows terminal (PowerShell / cmd)."""
    if IS_WINDOWS:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass  # Not critical


# ── Startup banner ─────────────────────────────────────────────────────────────
def print_platform_info():
    print(f"[Platform] {SYSTEM} {platform.release()} | Python {sys.version.split()[0]}")
    if IS_WINDOWS:
        print("[Platform] ✅ Windows compatibility mode active")
    elif IS_MAC:
        print("[Platform] ✅ macOS detected")
    else:
        print("[Platform] ✅ Linux detected")


# ── Run script helper ──────────────────────────────────────────────────────────
def run_command_instructions(persona: str) -> str:
    """Returns OS-appropriate run command for the README / help text."""
    if IS_WINDOWS:
        return (
            f"Windows CMD:        set PERSONA={persona} && python src/main.py\n"
            f"Windows PowerShell: $env:PERSONA='{persona}'; python src/main.py"
        )
    else:
        return f"Mac/Linux: PERSONA={persona} python src/main.py"


if __name__ == "__main__":
    print_platform_info()
    print(f"\nRun commands:")
    print(run_command_instructions("trump"))
    print(run_command_instructions("biden"))
