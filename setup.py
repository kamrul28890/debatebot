"""
setup.py

One-command setup for Debate Night.
Run: python setup.py

Does:
1. Checks Python version (3.10+)
2. Creates virtual environment
3. Installs all dependencies
4. Creates keys.py from template
5. Creates directory structure
6. Generates silent placeholder sounds
7. Prints final checklist
"""

import os
import sys
import subprocess
import shutil


def run(cmd, check=True):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=False)
    if check and result.returncode != 0:
        print(f"  ❌ Command failed: {cmd}")
        sys.exit(1)
    return result


def main():
    print("""
╔══════════════════════════════════════════════════╗
║       🏛️  DEBATE NIGHT — SETUP                  ║
║           Purdue ECE49595NL / ECE59500NL         ║
╚══════════════════════════════════════════════════╝
""")

    # ── Python version check ───────────────────────────────────────────────────
    if sys.version_info < (3, 10):
        print("❌ Python 3.10+ required.")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")

    # ── Create directories ─────────────────────────────────────────────────────
    print("\n📁 Creating directory structure...")
    dirs = [
        "data/raw_trump",
        "data/raw_biden",
        "data/raw_siskind",
        "data/crowd_sounds",
        "src/brain/personas",
        "src/audio",
        "src/gui",
        "src/moderator",
        "src/utils",
        "scripts",
        "logs",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"   ✅ {d}/")

    # ── Create __init__.py files ───────────────────────────────────────────────
    init_dirs = ["src", "src/audio", "src/brain", "src/gui", "src/moderator", "src/utils"]
    for d in init_dirs:
        init_path = os.path.join(d, "__init__.py")
        if not os.path.exists(init_path):
            open(init_path, "w").close()

    # ── keys.py ────────────────────────────────────────────────────────────────
    print("\n🔑 Checking API keys...")
    if not os.path.exists("keys.py"):
        shutil.copy("keys_template.py", "keys.py")
        print("   ✅ Created keys.py from template")
        print("   ⚠️  EDIT keys.py with your Azure credentials before running!")
    else:
        print("   ✅ keys.py already exists")

    # ── Install dependencies ───────────────────────────────────────────────────
    print("\n📦 Installing Python dependencies...")
    run(f"{sys.executable} -m pip install -r requirements.txt --quiet")
    print("   ✅ Dependencies installed")

    # ── Generate placeholder sounds ────────────────────────────────────────────
    print("\n🔊 Generating placeholder sound files...")
    run(f"{sys.executable} scripts/download_sounds.py", check=False)

    # ── Final checklist ────────────────────────────────────────────────────────
    print("""
╔══════════════════════════════════════════════════════════════╗
║  ✅ SETUP COMPLETE — Pre-flight checklist:                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. ✏️  Edit keys.py with your Azure API keys               ║
║                                                              ║
║  2. 🎤 Add reference voice files:                           ║
║     • data/raw_trump/ref.wav   (10-30s Trump speaking)      ║
║     • data/raw_biden/ref.wav   (10-30s Biden speaking)      ║
║     • data/raw_siskind/ref.wav (10-30s Siskind speaking)    ║
║                                                              ║
║  3. 🖼️  Add avatar images (already in zip):                 ║
║     • data/raw_trump/idle.png, talking.png, listening.png   ║
║     • data/raw_biden/idle.png, talking.png, listening.png   ║
║     • data/raw_siskind/idle.png, talking.png, listening.png ║
║                                                              ║
║  4. 🔊 Add real sound files (optional but recommended):     ║
║     • python scripts/download_sounds.py                     ║
║                                                              ║
║  5. 📊 Scrape speech data (optional, enriches persona):     ║
║     • python src/utils/scraper_trump.py                     ║
║     • python src/utils/scraper_biden.py                     ║
║                                                              ║
║  6. 🚀 Run the debate:                                      ║
║     Laptop A: PERSONA=trump python src/main.py              ║
║     Laptop B: PERSONA=biden python src/main.py              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
