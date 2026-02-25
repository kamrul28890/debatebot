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
  - `scripts/test_qwen_integration.py`
  - `scripts/upload_to_huggingface.py`
  - `scripts/doctor.py`

## Installation

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

## macOS Notes

- Use Python 3.10 (recommended for compatibility with all optional stacks).
- For XTTS on Apple Silicon, keep PyTorch/torchaudio in the same venv as TTS.
- First XTTS run downloads large model files; this is expected.

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
