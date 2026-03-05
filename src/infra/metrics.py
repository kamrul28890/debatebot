"""Lightweight runtime metrics for live debates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnMetric:
    persona: str
    round_index: int
    words: int
    listen_ms: float
    generate_ms: float
    speak_ms: float

    @property
    def total_ms(self) -> float:
        return self.listen_ms + self.generate_ms + self.speak_ms


class DebateMetrics:
    def __init__(self):
        self._turns: list[TurnMetric] = []

    def record_turn(
        self,
        persona: str,
        round_index: int,
        words: int,
        listen_ms: float,
        generate_ms: float,
        speak_ms: float,
    ) -> TurnMetric:
        metric = TurnMetric(
            persona=persona,
            round_index=round_index,
            words=max(0, int(words)),
            listen_ms=max(0.0, float(listen_ms)),
            generate_ms=max(0.0, float(generate_ms)),
            speak_ms=max(0.0, float(speak_ms)),
        )
        self._turns.append(metric)
        return metric

    def recent_summary(self, window: int = 6) -> str:
        if not self._turns:
            return "PERF: awaiting first turn"

        batch = self._turns[-max(1, window):]
        avg_gen = sum(t.generate_ms for t in batch) / len(batch)
        avg_speak = sum(t.speak_ms for t in batch) / len(batch)
        avg_total = sum(t.total_ms for t in batch) / len(batch)
        avg_words = sum(t.words for t in batch) / len(batch)
        return (
            "PERF: "
            f"avg_gen={avg_gen:.0f}ms | avg_tts={avg_speak:.0f}ms | "
            f"avg_turn={avg_total:.0f}ms | avg_words={avg_words:.0f}"
        )

    def to_dict(self) -> dict:
        return {
            "turns": [
                {
                    "persona": t.persona,
                    "round_index": t.round_index,
                    "words": t.words,
                    "listen_ms": t.listen_ms,
                    "generate_ms": t.generate_ms,
                    "speak_ms": t.speak_ms,
                    "total_ms": t.total_ms,
                }
                for t in self._turns
            ]
        }
