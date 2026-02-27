# Installation Guide

This guide is for a clean setup on Windows, macOS, or Linux.

## Course Submission Notes

For Brightspace submission, include code/docs only:
- Do not include downloaded model weights.
- Do not include trained model weights/checkpoints.
- Do not include local secrets (`keys.py`, `.env*`).

External model pointers used by this project:
- Qwen base model: `Qwen/Qwen2.5-0.5B` (Hugging Face)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face)
- XTTS model: `tts_models/multilingual/multi-dataset/xtts_v2` (Coqui TTS downloader)

Example zip command (macOS/Linux):
```bash
zip -r debatebot_submission.zip . \
  -x ".git/*" ".venv/*" "__pycache__/*" "*.pyc" \
     "data/models/*" "data/cache_sessions/*" "data/xtts_cache/*" ".rag_cache/*" \
     "keys.py" ".env" ".env.*"
```

## 0. One-command setup for first-time users (recommended)

Pick a module combo and run:
Run this after creating and activating your virtual environment.

```bash
python scripts/setup_selected_mode.py --persona trump --combo azure_robotic
```

Combo choices:
- `azure_robotic`
- `qwen_robotic`
- `azure_cloned`
- `qwen_cloned`

For dual-laptop full local demo:
```bash
python scripts/setup_selected_mode.py --persona trump --combo qwen_cloned
python scripts/setup_selected_mode.py --persona biden --combo qwen_cloned
```

## 1. Python Version

Use Python 3.10.x.

## 2. Create and activate virtual environment

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 3. Install dependencies

Recommended (single command, cross-stack conflict-safe):
```bash
python scripts/bootstrap.py --rag --qwen --xtts --doctor
```

Alternative (editable extras):
```bash
python -m pip install -e ".[rag,qwen,xtts]"
python -m pip check
```

Legacy split files:
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-rag.txt
python -m pip install -r requirements-qwen.txt
python -m pip install -r requirements-xtts.txt
python -m pip check
```

## 4. Configure credentials

Option A (preferred): environment variables
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

Option B: local file
```bash
copy keys_template.py keys.py   # Windows
cp keys_template.py keys.py     # macOS/Linux
```

Then fill the values in `keys.py`.

## 5. Add required local assets

Reference voice files:
- `data/raw_trump/ref.wav`
- `data/raw_biden/ref.wav`
- `data/raw_siskind/ref.wav`

## 6. Run diagnostics

```bash
python scripts/doctor.py
```

Full local stack:
```bash
python scripts/doctor.py --rag --qwen --xtts
```

## 7. Run the app

Windows PowerShell:
```powershell
$env:PERSONA="trump"
python src/main.py
```

macOS/Linux:
```bash
PERSONA=trump python src/main.py
```

Run another terminal with `PERSONA=biden`.

Recommended two-laptop live profile (host on Trump laptop):

Windows PowerShell:
```powershell
# Trump laptop
$env:PERSONA="trump"
$env:DEBATE_MODERATOR_MODE="host_only"
$env:DEBATE_HOST_PERSONA="trump"
$env:DEBATE_MAX_TURNS_PER_PERSONA="8"
$env:DEBATE_TARGET_SECONDS_PER_TURN="30"
python src/main.py

# Biden laptop
$env:PERSONA="biden"
$env:DEBATE_MODERATOR_MODE="host_only"
$env:DEBATE_HOST_PERSONA="trump"
$env:DEBATE_MAX_TURNS_PER_PERSONA="8"
$env:DEBATE_TARGET_SECONDS_PER_TURN="30"
python src/main.py
```

macOS/Linux:
```bash
PERSONA=trump DEBATE_MODERATOR_MODE=host_only DEBATE_HOST_PERSONA=trump DEBATE_MAX_TURNS_PER_PERSONA=8 DEBATE_TARGET_SECONDS_PER_TURN=30 python src/main.py
PERSONA=biden DEBATE_MODERATOR_MODE=host_only DEBATE_HOST_PERSONA=trump DEBATE_MAX_TURNS_PER_PERSONA=8 DEBATE_TARGET_SECONDS_PER_TURN=30 python src/main.py
```

GUI-first setup option:
- Launch `python src/main.py`
- In selector, choose module/persona
- Choose `Session` profile:
  - `Standard` for normal operation
  - `Live Host` on the moderator laptop
  - `Live Guest` on the other laptop
- Click `Auto Setup (<Selected Module>)`
- Watch progress in the right panel (non-blocking background task)

## 8. Qwen setup (optional)

1. Place:
   - `data/trump_train.jsonl`
   - `data/biden_train.jsonl`
2. Validate:
   - `python scripts/test_qwen_integration.py`
3. Train:
   - `python scripts/finetune_qwen.py --persona trump`
   - `python scripts/finetune_qwen.py --persona biden`
4. Optional upload:
   - `python scripts/upload_to_huggingface.py --model_path ... --repo_name ...`

## 9. Common issues

- Dependency conflicts:
  - Use split requirement files in this repository; avoid old frozen lockfiles.
- Wrong interpreter:
  - Always run commands with the `.venv` Python.
- XTTS missing:
  - Install `requirements-xtts.txt` and rerun doctor.
- Qwen missing:
  - Install `requirements-qwen.txt` and ensure local adapters or HF token.
- Two laptops out of sync in cached mode:
  - Compare `Session sync fingerprint` shown in selector status.
  - If mismatched, run `scripts/prepare_debate_cache.py --force` on both machines.
