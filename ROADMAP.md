# DebateBot Live-Only Roadmap

## Targets
- Startup to selector-ready: <= 4s on typical dev laptop.
- First candidate response: <= 2s Azure path, <= 3.5s Qwen path (warm state).
- Runtime stability: no crashes over 60-minute soak run.

## Milestone 1: Live-Only Core
- Remove cached/pre-recorded runtime paths.
- Enforce single debate state machine for all moderator modes.
- Move heavy runtime initialization into worker thread.

## Milestone 2: Performance + Reliability
- Add retry/backoff for generation/listening.
- Add runtime metrics and per-turn latency summaries.
- Add structured logging option (`DEBATE_LOG_JSON=1`).

## Milestone 3: Hardening + Delivery
- Expand unit and integration tests around orchestration.
- Keep docs and doctor tooling aligned to live-only scope.
- Maintain one-command bootstrap and diagnostics workflow.
