# Qwen Integration and Deployment Report

## 1. Scope and Goal

This work integrated Qwen 2.5 0.5B LoRA fine-tuning as a third-brain option in the debate app, verified end-to-end behavior, fixed runtime blockers, documented architecture/process, and prepared repository/cloud publishing.

## 2. What Was Present in Codebase

The repository already contained:
- `src/brain/qwen_brain.py` (Qwen runtime loader)
- `scripts/finetune_qwen.py` (LoRA training)
- `scripts/prepare_dataset.py` (dataset conversion)
- `scripts/test_qwen_integration.py` (validation script)
- `scripts/upload_to_huggingface.py` (HF upload)
- Qwen brain selection in `src/gui/voice_selector.py`
- Multi-backend selection in `src/brain/model.py` and `src/main.py`

## 3. Core Architecture and Component Responsibilities

### 3.1 Runtime path
- `src/main.py`
  - Starts mode selector and debate worker
  - Injects selected `brain_type` and `voice_mode`
- `src/brain/model.py`
  - Backend abstraction for Azure vs Qwen
  - RAG context retrieval and response orchestration
- `src/brain/qwen_brain.py`
  - Loads local LoRA adapter if available
  - Loads base model + merges adapter for inference
  - Generates text via HF pipeline

### 3.2 Fine-tuning path
- `scripts/prepare_dataset.py`
  - Converts raw text/JSONL to trainable JSONL rows
- `scripts/finetune_qwen.py`
  - Loads train data
  - Applies LoRA config on Qwen base model
  - Saves adapters + checkpoints to persona folders
- `scripts/upload_to_huggingface.py`
  - Pushes model folders to HF Hub repos

### 3.3 Voice and UI path
- `src/gui/voice_selector.py`
  - Four cards: 2 brain options x 2 voice options
- `src/audio/xtts_speaker.py` + `src/audio/speaker.py`
  - XTTS and Azure TTS modes

## 4. Process Followed

1. Audited repository against claimed implementation list.
2. Performed static checks and runtime smoke tests.
3. Identified integration and environment mismatches.
4. Trained persona adapters (`trump`, `biden`) and validated output load path.
5. Patched runtime loader and supporting scripts for robust behavior.
6. Reworked documentation for installation + Qwen workflow.
7. Prepared artifacts for Git push while excluding non-portable base cache.

## 5. Key Problems Encountered

### 5.1 Local adapter load failure (`config.json` missing)
- Symptom:
  - Runtime looked for base model at `data/models/qwen-2.5-0.5b-base` as if it were a full model root.
- Root cause:
  - Trainer cache structure under that folder is HF cache layout, not model root expected by `from_pretrained` with direct path.

### 5.2 Environment mismatch on Windows
- Symptom:
  - Commands worked in one interpreter and failed in another (`numpy`/`transformers` type errors).
- Root cause:
  - Multiple Python environments; global interpreter differed from `.venv`.

### 5.3 Validation script mismatches
- Symptom:
  - `scripts/test_qwen_integration.py` used stale API args (`QwenBrain(model_path=...)`, `generate_response(..., max_length=...)`).
- Root cause:
  - Script drifted behind current `QwenBrain` signature.

### 5.4 Requirements conflicts
- Symptom:
  - Duplicate `transformers` and contradictory `huggingface_hub` pins.
- Root cause:
  - App deps and Qwen deps appended without reconciliation.

### 5.5 Git push risk from base model cache
- Symptom:
  - `data/models/qwen-2.5-0.5b-base` contains ~988MB file (GitHub-blocking size).
- Root cause:
  - Base model cache not excluded from git patterns.

## 6. Fixes Applied

### 6.1 Qwen loader fix (critical)
File: `src/brain/qwen_brain.py`
- Added base-model source resolution priority:
  1. `QWEN_BASE_MODEL`
  2. adapter `base_model_name_or_path`
  3. local path only if `config.json` exists
  4. fallback `Qwen/Qwen2.5-0.5B`
- Added HF repo env support:
  - `HF_MODEL_REPO_TRUMP`, `HF_MODEL_REPO_BIDEN`, `HF_MODEL_REPO`
- Result:
  - Persona adapters load and generate correctly.

### 6.2 Brain backend fix
File: `src/brain/model.py`
- Fixed Azure deployment field assignment to use `keys.azure_openai_deployment`.
- Improved Qwen context injection to include recent conversation history.

### 6.3 Fine-tune dataset compatibility improvement
File: `scripts/finetune_qwen.py`
- Extended loader to handle instruction-style rows:
  - `instruction` + `input` + `output` -> merged training text.

### 6.4 Validation script rewrite
File: `scripts/test_qwen_integration.py`
- Updated to current API.
- Removed fragile Unicode-only output behavior.
- Made HF model info check robust to API object changes.

### 6.5 HF upload script guidance alignment
File: `scripts/upload_to_huggingface.py`
- Updated post-upload runtime instructions to match env vars now supported in `qwen_brain.py`.

### 6.6 Git ignore hardening for artifact policy
File: `.gitignore`
- Added ignores for base model cache and lock/cache internals under `data/models/qwen-2.5-0.5b-base/**`.
- Keeps fine-tuned adapters/checkpoints trackable.

### 6.7 README overhaul
File: `README.md`
- Replaced with a complete install + run + Qwen fine-tuning + troubleshooting guide.

## 7. Good vs Bad (Current State)

### Good
- Qwen local inference now works with trained adapters for both personas.
- Persona-separated training artifacts are compatible with runtime selection behavior.
- App supports four runtime combinations (2 brains x 2 voices).
- Fallback strategy remains intact (XTTS -> Azure TTS, local Qwen -> HF repo fallback when configured).

### Bad / Tradeoffs
- Qwen 0.5B quality is weaker than GPT-4 on coherence and factual reliability.
- CPU inference latency can still be noticeable.
- Model artifacts with checkpoints significantly increase repo size.
- Some docs/scripts still rely on external env correctness (`keys.py`, HF token).

## 8. What Could Not Be Fully Addressed Here

- Objective quality benchmarking between Azure and Qwen across standardized prompts was not executed.
- Full dual-instance live debate soak test (long-duration run with both personas continuously) was not fully captured in automated metrics.
- Hugging Face upload success depends on valid token/account permission at runtime.

## 9. Findings

1. The central blocker was not training quality but base-model resolution at inference.
2. Adapter metadata (`adapter_config.json`) is the most reliable source for base model path.
3. Environment discipline (`.venv` interpreter consistency) is essential on Windows.
4. Keeping base model cache out of git is mandatory for pushability and repository hygiene.

## 10. Conclusion

The Qwen path is now operational for local persona adapters and integrated into the app selection flow. The repository is documented and structured for reproducible setup and usage. Remaining limitations are primarily model-quality/latency tradeoffs inherent to a small local model and operational dependencies (credentials/tokens).
