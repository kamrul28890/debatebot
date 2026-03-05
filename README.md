# DebateBot (Live-Only)

Live AI presidential debate simulator with two candidates and two moderator modes.

## What It Does
- Candidates: Trump and Biden (always live generation)
- Brain backends (4 modules):
  - Azure + Robotic Voice
  - Qwen + Robotic Voice
  - Azure + Cloned Voice
  - Qwen + Cloned Voice
- Moderator modes:
  - Siskind AI moderator
  - User Moderator (Best): your prompt routes first speaker (addressed candidate starts, default is Trump)

## Architecture
- Entry point: `src/main.py`
- State machine: `src/core/debate_orchestrator.py`
- Runtime service bootstrap: `src/services/runtime.py`
- Runtime metrics: `src/infra/metrics.py`
- Brain abstraction: `src/brain/model.py`
- Audio backends: `src/audio/speaker.py`, `src/audio/xtts_speaker.py`
- GUI selector: `src/gui/voice_selector.py`
- Dashboard: `src/gui/dashboard.py`

## Install

### 1. Create and activate venv

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Install dependencies
```bash
python scripts/bootstrap.py --rag --qwen --xtts --doctor
```

### 3. Configure credentials
Preferred env vars:
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

Fallback:
```bash
cp keys_template.py keys.py
```
Then fill `keys.py`.

## Run
```bash
python src/main.py
```

Pick one of the 4 modules and moderator mode in the selector.

## Keyboard Controls
- `F`: toggle fact checker
- `C`: manual applause
- `R`: reset debate state
- `Esc`: quit

## Diagnostics
```bash
python scripts/doctor.py --rag --qwen --xtts
```

Optional JSON logs:
```bash
DEBATE_LOG_JSON=1 python src/main.py
```

## Project Roadmap
See `ROADMAP.md` for milestones and rollout sequencing.
