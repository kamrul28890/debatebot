# Debate Night (Cross-Platform)

AI presidential debate simulator for Purdue ECE49595NL / ECE59500NL (Spring 2026).

The app runs two personas (Trump/Biden) with:
- Brain mode: Azure GPT-4 or local Qwen 2.5 0.5B (LoRA fine-tuned)
- Voice mode: Azure Neural TTS or XTTS voice clone
- RAG quote retrieval from local speech corpora
- Fact-check overlay, moderator, and live dashboard

## 1. Architecture Overview

### Entry Point
- `src/main.py`
  - Starts mode selector, dashboard, and debate worker thread
  - Passes selected `brain_type` and `voice_mode` into runtime

### Brain Layer
- `src/brain/model.py`
  - `DebateBrain` abstraction
  - Backends:
    - `azure`: Azure OpenAI deployment
    - `qwen`: local/HF-backed `QwenBrain`
- `src/brain/qwen_brain.py`
  - Loads local LoRA adapter when present
  - Resolves base model from adapter metadata (`base_model_name_or_path`) or fallback
  - Optional HF fallback via repo env vars
- `src/brain/rag.py`
  - Local sentence-transformer retrieval over `data/raw_<persona>/speeches.txt`

### Audio Layer
- `src/audio/xtts_speaker.py`
  - XTTS synthesis and cache playback
  - Automatic fallback to Azure TTS
- `src/audio/speaker.py`
  - Azure Neural TTS with persona-tuned SSML
- `src/audio/listener.py`
  - Azure STT listener with mute window for echo suppression

### GUI / Moderator
- `src/gui/voice_selector.py`
  - Startup selector for 2 brain cards + 2 voice cards
- `src/gui/dashboard.py`
  - Debate dashboard, ticker, fact-check overlay
- `src/moderator/siskind.py`
  - Moderator prompts and interjections

### Qwen Tooling
- `scripts/prepare_dataset.py`
- `scripts/finetune_qwen.py`
- `scripts/test_qwen_integration.py`
- `scripts/upload_to_huggingface.py`

## 2. Prerequisites

- Python 3.10.x
- Microphone + speakers
- Azure credentials in `keys.py` for STT/TTS and Azure brain mode
- Internet for first model downloads (XTTS and Qwen base)
- Recommended for Qwen fine-tuning on CPU: 48GB RAM

## 3. Environment Setup

### Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Keys
```powershell
copy keys_template.py keys.py
```
(or `cp keys_template.py keys.py` on macOS/Linux)

Fill:
- `azure_openai_key`
- `azure_openai_endpoint`
- `azure_openai_api_version`
- `azure_openai_deployment`
- `azure_key`
- `azure_region`

## 4. Running the App

```powershell
$env:PERSONA="trump"
.\.venv\Scripts\python.exe src/main.py
```

Second instance:
```powershell
$env:PERSONA="biden"
.\.venv\Scripts\python.exe src/main.py
```

At startup, choose one brain card and one voice card.

## 5. Qwen Fine-Tuning (Detailed)

### 5.1 Dataset Files
Place:
- `data/trump_train.jsonl`
- `data/biden_train.jsonl`

Supported JSONL row formats in current trainer:
- `{"text": "..."}`
- `{"messages": [{"role": "user", "content": "..."}, ...]}`
- `{"instruction": "...", "input": "...", "output": "..."}`

If your raw data is plain text:
```powershell
.\.venv\Scripts\python.exe scripts\prepare_dataset.py --input_file your_trump_data.txt --output_file data\trump_train.jsonl --persona trump
.\.venv\Scripts\python.exe scripts\prepare_dataset.py --input_file your_biden_data.txt --output_file data\biden_train.jsonl --persona biden
```

### 5.2 Integration Precheck
```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe scripts\test_qwen_integration.py
```

### 5.3 Train Persona Adapters (Recommended)
Train separate adapters for stronger persona style:
```powershell
.\.venv\Scripts\python.exe scripts\finetune_qwen.py --persona trump
.\.venv\Scripts\python.exe scripts\finetune_qwen.py --persona biden
```

Outputs:
- `data/models/qwen-2.5-0.5b-finetuned-trump/`
- `data/models/qwen-2.5-0.5b-finetuned-biden/`

### 5.4 Validate Adapter Inference
```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -c "from src.brain.qwen_brain import QwenBrain; b=QwenBrain('trump'); print(b.generate_response('Why are your policies better?')[:300])"
.\.venv\Scripts\python.exe -c "from src.brain.qwen_brain import QwenBrain; b=QwenBrain('biden'); print(b.generate_response('Why are your policies better?')[:300])"
```

### 5.5 Connect Qwen to Runtime
No extra code changes needed if those local folders exist. Selector will detect them.

Optional env overrides:
- `QWEN_BASE_MODEL` (path or HF repo for base)
- `HF_MODEL_REPO_TRUMP`
- `HF_MODEL_REPO_BIDEN`
- `HF_MODEL_REPO` (shared fallback)

## 6. Upload Fine-Tuned Models to Hugging Face

```powershell
.\.venv\Scripts\python.exe scripts\upload_to_huggingface.py --model_path data\models\qwen-2.5-0.5b-finetuned-trump --repo_name <username>/qwen-debate-trump
.\.venv\Scripts\python.exe scripts\upload_to_huggingface.py --model_path data\models\qwen-2.5-0.5b-finetuned-biden --repo_name <username>/qwen-debate-biden
```

For runtime HF fallback, set:
```powershell
$env:HF_MODEL_REPO_TRUMP="<username>/qwen-debate-trump"
$env:HF_MODEL_REPO_BIDEN="<username>/qwen-debate-biden"
```

## 7. Troubleshooting

### Error: missing `config.json` in `data/models/qwen-2.5-0.5b-base`
Cause: base model cache directory is not a direct HF model folder root.

Fix: use current `qwen_brain.py` logic (already handled) and run with `.venv` interpreter.

### Wrong Python environment / weird `transformers`-`numpy` errors
Use explicit interpreter:
```powershell
.\.venv\Scripts\python.exe <command>
```

### Qwen import fails (`peft`/`datasets`/`accelerate` missing)
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### XTTS unavailable
Fallback to Azure TTS is automatic. Install missing deps if needed:
```powershell
.\.venv\Scripts\python.exe -m pip install TTS torch torchaudio
```

## 8. Git/Artifact Policy in This Repo

Ignored by git:
- `keys.py`
- logs/caches (`logs/`, `.rag_cache/`, `data/xtts_cache/`)
- local Qwen base cache (`data/models/qwen-2.5-0.5b-base/**`)

Tracked (as requested):
- fine-tuned adapter outputs and checkpoints under:
  - `data/models/qwen-2.5-0.5b-finetuned-trump/**`
  - `data/models/qwen-2.5-0.5b-finetuned-biden/**`

## 9. Useful Commands

```powershell
# Compile sanity check
.\.venv\Scripts\python.exe -m compileall -q src scripts

# Run Qwen integration test
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe scripts\test_qwen_integration.py
```
