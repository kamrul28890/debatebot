# Debate Night (Cross-Platform)

AI presidential debate simulator with selectable brain and voice backends:
- Brain: Azure OpenAI GPT or local Qwen 2.5 0.5B LoRA
- Voice: Azure Neural TTS or local XTTS voice cloning
- Extras: RAG quote retrieval, fact-check overlay, moderator, live dashboard

## Architecture

- Entry point: `src/main.py`
- Brain abstraction: `src/brain/model.py`
- Local Qwen runtime: `src/brain/qwen_brain.py`
- RAG retrieval: `src/brain/rag.py`
- Voice backends: `src/audio/speaker.py`, `src/audio/xtts_speaker.py`
- GUI mode selector: `src/gui/voice_selector.py`
- Qwen tooling:
  - `scripts/prepare_dataset.py`
  - `scripts/finetune_qwen.py`
  - `scripts/setup_selected_mode.py`
  - `scripts/prepare_debate_cache.py`
  - `scripts/download_sounds.py`
  - `scripts/test_qwen_integration.py`
  - `scripts/upload_to_huggingface.py`
  - `scripts/doctor.py`

## Course Submission Compliance

This repository is prepared for the course submission constraints:
- No downloaded software or model weights are committed.
- No trained model weights are committed.
- The repo contains code to reproduce training and setup, not trained artifacts.
- Team demos are two-laptop, speech-only debates (no bot-to-bot network link).

Pointers for externally downloaded assets/models:
- Qwen base model: `Qwen/Qwen2.5-0.5B` (Hugging Face)
- Sentence embedding model: `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face)
- XTTS model: `tts_models/multilingual/multi-dataset/xtts_v2` (downloaded by Coqui TTS)
- Audio/media provenance: `data/SOURCES.md` and `data/crowd_sounds/SOURCES.json`

To build a submission zip (code/docs only), run:
```bash
zip -r debatebot_submission.zip . \
  -x ".git/*" ".venv/*" "__pycache__/*" "*.pyc" \
     "data/models/*" "data/cache_sessions/*" "data/xtts_cache/*" ".rag_cache/*" \
     "keys.py" ".env" ".env.*"
```

## Installation

### 0. Fastest First-Time Setup (Recommended)

If you want a single command that installs dependencies, prepares cache, and validates a selected module:
Run this after creating and activating your virtual environment.

```bash
python scripts/setup_selected_mode.py --persona trump --combo azure_robotic
```

Other combos:
- `azure_robotic`
- `qwen_robotic`
- `azure_cloned`
- `qwen_cloned`

Examples:
```bash
python scripts/setup_selected_mode.py --persona trump --combo qwen_cloned
python scripts/setup_selected_mode.py --persona biden --combo qwen_cloned
```

### 1. Create a virtual environment

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

### 2. Install dependencies

Recommended (single resolver pass, lowest conflict risk):
```bash
python scripts/bootstrap.py --rag --qwen --xtts --doctor
```

Alternative (editable install with extras):
```bash
python -m pip install -e ".[rag,qwen,xtts]"
python -m pip check
```

Optional legacy split install:
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-rag.txt
python -m pip install -r requirements-qwen.txt
python -m pip install -r requirements-xtts.txt
python -m pip check
```

### 3. Run environment diagnostics
```bash
python scripts/doctor.py
```

To automatically fetch crowd reaction SFX:
```bash
python scripts/download_sounds.py
```

For full local stack validation:
```bash
python scripts/doctor.py --rag --qwen --xtts
```

## Credentials

Preferred: environment variables
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`
- Optional voice overrides:
  - `AZURE_TTS_VOICE_TRUMP`
  - `AZURE_TTS_VOICE_BIDEN`
  - `AZURE_TTS_VOICE_SISKIND`

Fallback:
```bash
cp keys_template.py keys.py
```
Then fill `keys.py`.

## Run the app

Windows PowerShell:
```powershell
$env:PERSONA="trump"
python src/main.py
```

macOS/Linux:
```bash
PERSONA=trump python src/main.py
```

Start a second instance with `PERSONA=biden`.

At startup, choose:
- Brain: `azure` or `qwen`
- Voice: `azure` or `xtts`

Setup from GUI:
- Click `Auto Setup (<Selected Module>)` in the selector for one-click setup.
- Use `Prepare Cache (<Selected Module>)` to prebuild deterministic + XTTS assets in background with progress.
- Use `Session` profile buttons:
  - `Standard`: no session env overrides
  - `Live Host`: enables 8-turn, ~30s profile and runs moderator on this laptop
  - `Live Guest`: enables 8-turn, ~30s profile and expects moderator on the other laptop

## Two-Laptop Cached Debate (Recommended for Demo)

For smooth synchronized debates:

1. On Trump laptop:
```bash
python scripts/setup_selected_mode.py --persona trump --combo qwen_cloned
```

2. On Biden laptop:
```bash
python scripts/setup_selected_mode.py --persona biden --combo qwen_cloned
```

3. On both laptops, confirm same cache sync fingerprint:
- In selector status panel: `Session sync fingerprint: <hash>`
- In runtime ticker (cached mode): `CACHE: session sync fingerprint <hash>`

4. Start both in `Cached` mode.

GUI-first two-laptop launch:
- Trump laptop: select persona `Trump`, click `Session -> Live Host`, then start.
- Biden laptop: select persona `Biden`, click `Session -> Live Guest`, then start.

If fingerprints differ, rebuild cache on both laptops with:
```bash
python scripts/prepare_debate_cache.py --persona trump --voice xtts --force
python scripts/prepare_debate_cache.py --persona biden --voice xtts --force
```

## Qwen Fine-Tuning Workflow

### 1. Prepare dataset files
Place these files:
- `data/trump_train.jsonl`
- `data/biden_train.jsonl`

Supported row formats:
- `{"text": "..."}`
- `{"messages": [{"role":"user","content":"..."}, ...]}`
- `{"instruction":"...","input":"...","output":"..."}`

### 2. Validate integration
```bash
python scripts/test_qwen_integration.py
```

### 3. Train persona adapters
Recommended: train separate adapters for each persona.
```bash
python scripts/finetune_qwen.py --persona trump
python scripts/finetune_qwen.py --persona biden
```

Output directories:
- `data/models/qwen-2.5-0.5b-finetuned-trump/`
- `data/models/qwen-2.5-0.5b-finetuned-biden/`

### 4. Quick inference check
```bash
python -c "from src.brain.qwen_brain import QwenBrain; b=QwenBrain('trump'); print(b.generate_response('Why are your policies better?')[:300])"
python -c "from src.brain.qwen_brain import QwenBrain; b=QwenBrain('biden'); print(b.generate_response('Why are your policies better?')[:300])"
```

### 5. Optional: upload adapters to Hugging Face
```bash
python scripts/upload_to_huggingface.py --model_path data/models/qwen-2.5-0.5b-finetuned-trump --repo_name <username>/ai-debate-trump-biden-trump
python scripts/upload_to_huggingface.py --model_path data/models/qwen-2.5-0.5b-finetuned-biden --repo_name <username>/ai-debate-trump-biden-biden
```

Runtime fallback env vars:
- `HF_MODEL_REPO_TRUMP`
- `HF_MODEL_REPO_BIDEN`
- `HF_MODEL_REPO`
- `QWEN_BASE_MODEL` (optional override)

Live debate profile env vars:
- `DEBATE_MAX_TURNS_PER_PERSONA` (default `8`)
- `DEBATE_TARGET_SECONDS_PER_TURN` (default `30`)
- `DEBATE_WORDS_PER_SECOND` (default `2.1`, used for pacing/mute windows)
- `DEBATE_TOPIC_ROTATION_TURNS` (default `1`)
- `DEBATE_MODERATOR_MODE` (`host_only` default, or `both` / `off`)
- `DEBATE_HOST_PERSONA` (`trump` default)

## macOS Notes

- Use Python 3.10 (recommended for compatibility with all optional stacks).
- For XTTS on Apple Silicon, keep PyTorch/torchaudio in the same venv as TTS.
- First XTTS run downloads large model files; this is expected.

## Two-Laptop Live Debate (8-minute profile)

Recommended for stage demos where Trump and Biden run on separate laptops and alternate ~30 second turns:

1. Trump laptop (host moderator + candidate):
```powershell
$env:PERSONA="trump"
$env:DEBATE_MODERATOR_MODE="host_only"
$env:DEBATE_HOST_PERSONA="trump"
$env:DEBATE_MAX_TURNS_PER_PERSONA="8"
$env:DEBATE_TARGET_SECONDS_PER_TURN="30"
python src/main.py
```

2. Biden laptop (candidate channel, listens to host moderator prompts):
```powershell
$env:PERSONA="biden"
$env:DEBATE_MODERATOR_MODE="host_only"
$env:DEBATE_HOST_PERSONA="trump"
$env:DEBATE_MAX_TURNS_PER_PERSONA="8"
$env:DEBATE_TARGET_SECONDS_PER_TURN="30"
python src/main.py
```

The built-in topic slate now includes:
- Economy, immigration, healthcare, war/foreign policy
- Epstein files transparency
- Hunter Biden pardon ethics
- Trump legal exposure and election integrity
- China/trade/debt

## Troubleshooting

- Install conflict on non-macOS from `pyobjc`: fixed by split dependency files in this repo. Do not use old frozen lockfiles.
- Install conflicts across optional stacks:
  - Prefer one-shot install (`python scripts/bootstrap.py --rag --qwen --xtts`) over many separate pip commands.
- `config.json` missing under local base model path:
  - `qwen_brain.py` resolves base model from adapter metadata and HF fallback.
- Wrong environment:
  - Use explicit interpreter: `.\.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (macOS/Linux).
- Quick health check:
  - `python -m compileall -q src scripts`
  - `python scripts/doctor.py --rag --qwen --xtts`

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
python -m compileall -q src scripts tests
```

CI is configured in `.github/workflows/ci.yml` to run compile + smoke tests on Windows/macOS/Linux.
