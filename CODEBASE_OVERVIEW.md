# Codebase Overview (Live-Only)

## Runtime flow
1. `src/main.py` starts UI selector.
2. User chooses one of 4 live modules and moderator mode.
3. `DebateWorker` boots heavy services in worker thread.
4. `DebateOrchestrator` drives states:
   - `WAIT_MODERATOR`
   - `SPEAKER_1`
   - `SPEAKER_2`
   - `COMPLETE`
5. Debate repeats until per-persona turn limit is reached.

## Primary modules
- `src/core/debate_orchestrator.py`: state machine and speaker routing.
- `src/services/runtime.py`: bootstrap for brains, speakers, STT, moderator, fact checker.
- `src/infra/metrics.py`: turn-level timing metrics.
- `src/gui/voice_selector.py`: 4 module options + moderator mode selector.
- `src/gui/dashboard.py`: live stage, moderator panel, fact-check overlay, ticker.

## Audio policy
- Applause-only sound profile.
- No automatic boo/laugh/fanfare/fact-check sounds.

## Reliability features
- Runtime bootstrap in background thread.
- Generation retry/backoff.
- Fact-check graceful fallback when Azure OpenAI is unavailable.
- Structured logs available via `DEBATE_LOG_JSON=1`.

## Tests
- `tests/test_orchestrator.py`: state transitions and user prompt routing.
- `tests/test_repo_layout.py`: required live-only files.
- `tests/test_setup_selected_mode.py`: setup script CLI sanity.
