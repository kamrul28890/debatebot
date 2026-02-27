# Professional Review and Streamlining Plan

This review is written from a first-time external engineer perspective, prioritizing:
- user friendliness
- smooth software experience
- easy navigation
- reliable cross-platform behavior (Windows + macOS)
- dual-laptop debate synchronization

## Critical findings

1. First-time setup had too many manual branches.
- Users had to decide dependency sets, training, and cache prep manually.
- Result: frequent half-configured states and confusion.

2. Dual-laptop cached debate could drift silently.
- Deterministic cache script existed, but no explicit fingerprint check was surfaced to operators.

3. Setup discoverability in GUI was fragmented.
- Multiple buttons existed but no single “do it all for this module” path.

4. Runtime diagnostics were good but not complete for onboarding scripts.
- Doctor didn’t validate the new automation scripts and deterministic cache script in one place.

## High-priority improvements implemented

1. Added one-click selected-module setup pipeline.
- New script: `scripts/setup_selected_mode.py`
- Handles:
  - dependency install for selected module
  - Qwen training if needed (or HF fallback)
  - deterministic/XTTS cache prep
  - doctor validation
- Emits progress lines for GUI integration.

2. Added GUI auto-setup action.
- New selector button: `Auto Setup (<Selected Module>)`
- Runs background setup task with progress bar and task log.
- Preserves responsive UI.

3. Added explicit dual-laptop sync fingerprint visibility.
- Selector now computes and shows deterministic script fingerprint.
- Runtime ticker shows the same fingerprint in cached mode.
- Operators can verify both laptops are aligned before starting.

4. Expanded doctor coverage.
- Doctor now checks:
  - `scripts/setup_selected_mode.py`
  - `scripts/prepare_debate_cache.py`
  - deterministic cache script readability + sync fingerprint

## Medium-priority recommendations (next pass)

1. Split large UI/controller modules.
- `src/gui/voice_selector.py` and `src/main.py` are still too large.
- Refactor into smaller service/controller classes for maintainability.

2. Add structured integration tests.
- Add smoke tests for:
  - selector start actions
  - setup script argument matrix
  - cached mode startup path

3. Strengthen secrets hygiene.
- Keep `keys.py` strictly local.
- Add pre-commit secret scanning and CI gate.

4. Add release packaging docs.
- Include reproducible “demo profile” bundles for teammates (assets + cache manifest + versions).

5. Improve operational telemetry.
- Add structured JSON logs for setup and runtime to simplify debugging during demos.

## Suggested team runbook

1. Clone repo.
2. Create venv and activate.
3. Run one command per persona:
   - `python scripts/setup_selected_mode.py --persona trump --combo qwen_cloned`
   - `python scripts/setup_selected_mode.py --persona biden --combo qwen_cloned`
4. Confirm both laptops show the same session sync fingerprint in selector.
5. Start both in cached mode.

