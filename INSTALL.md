# Installation Guide (Live-Only)

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

Recommended:
```bash
python scripts/bootstrap.py --rag --qwen --xtts --doctor
```

Alternative:
```bash
python -m pip install -e ".[rag,qwen,xtts]"
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
cp keys_template.py keys.py
```
Then fill values in `keys.py`.

## 5. Required local assets

Reference voice files:
- `data/raw_trump/ref.wav`
- `data/raw_biden/ref.wav`
- `data/raw_siskind/ref.wav` (for Siskind moderator mode)

## 6. Diagnostics
```bash
python scripts/doctor.py --rag --qwen --xtts
```

## 7. Run the app
```bash
python src/main.py
```

Use the selector to choose:
- One of 4 live modules
- Moderator mode (`Siskind AI` or `User Moderator (Best)`)

## 8. Optional Qwen training flow
1. Place datasets:
   - `data/trump_train.jsonl`
   - `data/biden_train.jsonl`
2. Validate:
   - `python scripts/test_qwen_integration.py`
3. Train:
   - `python scripts/finetune_qwen.py --persona trump`
   - `python scripts/finetune_qwen.py --persona biden`

## 9. Common issues
- Dependency conflicts: use `scripts/bootstrap.py` first.
- XTTS issues: install xtts deps and ensure `ref.wav` files exist.
- Qwen issues: install qwen deps and ensure local adapters or HF token fallback.
