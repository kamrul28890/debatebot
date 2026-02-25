# Installation Guide

This guide is for a clean setup on Windows, macOS, or Linux.

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

Core app:
```bash
python -m pip install -r requirements.txt
```

Optional feature packs:
```bash
python -m pip install -r requirements-rag.txt
python -m pip install -r requirements-qwen.txt
python -m pip install -r requirements-xtts.txt
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

