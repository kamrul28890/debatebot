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
- Voice mode is selected at startup (`AZURE` or `XTTS`).
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
    xtts_cache/          # generated at runtime
  scripts/
  keys_template.py
  requirements.txt
  setup.py
```

## Prerequisites

- Python 3.10 (recommended for current dependency set)
- Working microphone and speaker
- Azure keys (for OpenAI + Speech paths)
- Internet access for first XTTS model download

## Setup

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
- `data/raw_trump/ref.wav`
- `data/raw_biden/ref.wav`
- `data/raw_siskind/ref.wav`

Recommended avatar images:
- `idle.png`, `talking.png`, `listening.png` in each `data/raw_*` folder

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

