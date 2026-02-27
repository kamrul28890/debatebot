# Brightspace Submission Checklist

Use this checklist before each teammate submits the team zip.

## Must Include

- Source code (`src/`, `scripts/`, tests, config files)
- Documentation (`README.md`, `INSTALL.md`, this checklist)
- Training code (`scripts/finetune_qwen.py`) and setup code (`scripts/bootstrap.py`, `scripts/setup_selected_mode.py`)

## Must Not Include

- Downloaded model weights (base/foundation models)
- Trained model weights/checkpoints (`data/models/...`)
- Local runtime caches (`data/xtts_cache`, `data/cache_sessions`, `.rag_cache`)
- Secrets (`keys.py`, `.env*`)

## External Asset Pointers

- Qwen base model: `Qwen/Qwen2.5-0.5B` on Hugging Face
- Sentence embeddings: `sentence-transformers/all-MiniLM-L6-v2` on Hugging Face
- XTTS model: `tts_models/multilingual/multi-dataset/xtts_v2` via Coqui TTS
- Media provenance: `data/SOURCES.md`, `data/crowd_sounds/SOURCES.json`

## Packaging Command (macOS/Linux)

```bash
zip -r debatebot_submission.zip . \
  -x ".git/*" ".venv/*" "__pycache__/*" "*.pyc" \
     "data/models/*" "data/cache_sessions/*" "data/xtts_cache/*" ".rag_cache/*" \
     "keys.py" ".env" ".env.*"
```

## In-Class Demo Constraint

- Bring two laptops: one Trump persona and one Biden persona.
- Systems debate through speech/audio only; no network channel between bots.
