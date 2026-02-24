# Debate Night

AI presidential debate simulator for Purdue ECE49595NL / ECE59500NL (Spring 2026).

Two personas (Trump or Biden) respond to live input with:
- GPT-based response generation
- RAG over local speech corpora
- Optional fact checking
- Voice output via Azure TTS or Coqui XTTS voice cloning
- PyQt6 debate dashboard

## Current Status

- Cross-platform run path (Windows/macOS/Linux) is in `src/main.py`.
- Voice mode is selected at startup (`AZURE` or `XTTS` - XTTS is auto-selected if available).
- XTTS first run downloads a large model (~1.5 GB) and can take 15-30s per long utterance on CPU.
- Moderator prompt handoff is supported to avoid deadlock when both listen/speak on one machine.

## Project Layout

```text
debate_night/
  src/
    main.py
    audio/
    brain/
    gui/
    moderator/
    utils/
  data/
    raw_trump/
    raw_biden/
    raw_siskind/
    crowd_sounds/
    xtts_cache/          # generated at runtime (ignored by git)
  scripts/
  keys_template.py
  requirements.txt
  setup.py
```

## Prerequisites

- Python 3.10+ (tested with 3.10.5)
- Working microphone and speaker
- Azure keys (for OpenAI + Speech paths)
- Internet access for first XTTS model download
- At least 8GB RAM (for XTTS model loading)

## Quick Start Installation

### 1) Clone the Repository

```bash
git clone <your-github-repo-url>
cd debatebot
```

### 2) Create and Activate Virtual Environment

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3) Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This will install all required packages including PyQt6, TTS, transformers, torch, etc.

### 4) Configure API Keys

```bash
cp keys_template.py keys.py
```

Edit `keys.py` with your Azure OpenAI and Speech credentials:
- `azure_openai_key`
- `azure_openai_endpoint`
- `azure_key`
- `azure_region`

### 5) Verify Setup

The repository includes:
- Reference voice files (`data/raw_*/ref.wav`) for XTTS voice cloning
- Avatar images for the GUI
- All necessary scripts and configurations

No additional downloads or setup required beyond keys!

## Run the Debate

**Trump instance:**
```bash
# macOS/Linux
PERSONA=trump python src/main.py

# Windows PowerShell
$env:PERSONA="trump"; python src/main.py

# Or use the provided script
./run_trump.sh
```

**Biden instance:**
```bash
PERSONA=biden python src/main.py
# Or
./run_biden.sh
```

## Voice Modes

The application automatically selects **XTTS voice cloning** if available (recommended for realistic voices), otherwise falls back to **Azure TTS**.

### XTTS (Voice Cloning)
- Clones voice from included `ref.wav` files
- Sounds like the real Trump/Biden/Siskind
- Uses `data/xtts_cache/` for generated audio (auto-created)
- First run downloads ~1.5GB model
- Better quality but slower initial synthesis

### Azure (Fallback)
- Real-time TTS with prosody tuning
- Faster startup, always available
- Generic voice quality

## Keyboard Controls

- `SPACE`: Force opening statement
- `M`: Moderator interject with new topic
- `F`: Toggle fact checker on/off
- `C`: Trigger crowd reaction
- `R`: Reset conversation history
- `ESC`: Quit debate

## Troubleshooting

### No Audio Output
- Check system audio settings
- Test audio with: `python -c "import pygame; pygame.mixer.init(); pygame.mixer.music.load('data/raw_trump/ref.wav'); pygame.mixer.music.play()"`
- Ensure microphone permissions

### XTTS Issues
- If XTTS loads but sounds robotic: Check that `data/raw_<persona>/ref.wav` exists
- Clear cache: `rm -rf data/xtts_cache/<persona>/`
- Model download issues: Ensure stable internet connection

### Import Errors
- Verify Python 3.10+ is used
- Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`

### GUI Doesn't Start
- Ensure display server (X11 on Linux, native on macOS/Windows)
- Check PyQt6 installation

## Advanced Setup

### Pre-generate XTTS Audio Cache
For zero-latency during debate:
```bash
python src/audio/xtts_speaker.py --pregenerate trump --texts "Hello" "I disagree" "That's not true"
```

### Custom Voice References
Replace `data/raw_*/ref.wav` with your own 10-30s clean speech samples.

### Crowd Sounds
Run `python scripts/download_sounds.py` or add `.wav` files to `data/crowd_sounds/`.

## Notes

- `keys.py` is gitignored - never commit API keys
- Virtual environment (`venv/`) is gitignored
- Cache folders and generated audio are gitignored
- Reference voice files are included in the repository
- Compatible with macOS, Windows, and Linux

### 1) Create and activate virtual environment

Windows PowerShell:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2) Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3) Configure keys

```bash
copy keys_template.py keys.py    # Windows
# or
cp keys_template.py keys.py      # macOS/Linux
```

Fill `keys.py` with your Azure/OpenAI credentials.

### 4) Add required media assets

Required voice references:
- `data/raw_trump/ref.wav` ✅ (included in repo)
- `data/raw_biden/ref.wav` ✅ (included in repo)
- `data/raw_siskind/ref.wav` ✅ (included in repo)

Recommended avatar images:
- `idle.png`, `talking.png`, `listening.png` in each `data/raw_*` folder ✅ (included)

Optional crowd sounds:
- Run `python scripts/download_sounds.py`
- Or drop `.wav` files into `data/crowd_sounds/`

## Run

Trump instance:
```powershell
$env:PERSONA="trump"
python src/main.py
```

Biden instance:
```powershell
$env:PERSONA="biden"
python src/main.py
```

Keyboard controls:
- `SPACE`: force opening statement
- `M`: moderator interject
- `F`: toggle fact checker
- `C`: crowd reaction
- `R`: reset debate history
- `ESC`: quit

## Voice Modes

### Azure
- Lower startup latency
- Good fallback if XTTS dependencies are missing

### XTTS
- Cloned timbre from `ref.wav` per persona
- Uses `data/xtts_cache/` for generated clips
- Better with clean 10-30s reference speech

## Troubleshooting

- No audio output:
  - Confirm system output device is active and not muted.
  - Test simple audio playback outside app.
  - Ensure `pygame` is installed and importable.
- XTTS selected but sounds generic:
  - Confirm `data/raw_<persona>/ref.wav` exists and is clean.
  - Delete persona cache in `data/xtts_cache/<persona>/` and rerun.
  - Ensure `TTS`, `torch`, and `torchaudio` are installed.
- XTTS appears stuck on first line:
  - First synthesis on CPU can be slow; wait for model warmup.
  - Check terminal logs for synthesis progress/fallback messages.
- Missing crowd sounds warnings:
  - Add files in `data/crowd_sounds/` or run `scripts/download_sounds.py`.

## Notes

- `keys.py` is intentionally ignored by git.
- `venv/`, cache folders, and generated audio are ignored by git.
- If you run both candidates on one machine, microphone/speaker bleed can still affect turn-taking.

