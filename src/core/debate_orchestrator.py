"""Live debate state machine and speaker routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class DebateState(str, Enum):
    WAIT_MODERATOR = "wait_moderator"
    SPEAKER_1 = "speaker_1"
    SPEAKER_2 = "speaker_2"
    COMPLETE = "complete"
    STOPPED = "stopped"


@dataclass(frozen=True)
class RoundPlan:
    moderator_prompt: str
    first_speaker: str
    second_speaker: str


class DebateOrchestrator:
    """Tracks turn limits, debate state, and first-speaker routing."""

    def __init__(self, max_turns_per_persona: int, starting_persona: str = "trump"):
        self.max_turns_per_persona = max(1, int(max_turns_per_persona))
        self.turns_spoken = {"trump": 0, "biden": 0}
        self.state = DebateState.WAIT_MODERATOR
        self._siskind_round_starter = starting_persona if starting_persona in {"trump", "biden"} else "trump"

    @staticmethod
    def other_persona(persona: str) -> str:
        return "biden" if persona == "trump" else "trump"

    def can_continue(self) -> bool:
        return self.state not in {DebateState.COMPLETE, DebateState.STOPPED} and not self.debate_complete()

    def debate_complete(self) -> bool:
        return all(count >= self.max_turns_per_persona for count in self.turns_spoken.values())

    def stop(self) -> None:
        self.state = DebateState.STOPPED

    def reset(self) -> None:
        self.turns_spoken = {"trump": 0, "biden": 0}
        self.state = DebateState.WAIT_MODERATOR
        self._siskind_round_starter = "trump"

    def next_user_round(self, moderator_prompt: str) -> RoundPlan:
        first = self.choose_first_speaker(moderator_prompt)
        second = self.other_persona(first)
        first, second = self._respect_turn_limits(first, second)
        self.state = DebateState.SPEAKER_1
        return RoundPlan(moderator_prompt=moderator_prompt, first_speaker=first, second_speaker=second)

    def next_siskind_round(self, moderator_prompt: str) -> RoundPlan:
        first = self._siskind_round_starter
        second = self.other_persona(first)
        first, second = self._respect_turn_limits(first, second)
        self._siskind_round_starter = second
        self.state = DebateState.SPEAKER_1
        return RoundPlan(moderator_prompt=moderator_prompt, first_speaker=first, second_speaker=second)

    def begin_second_speaker(self) -> None:
        if self.state != DebateState.STOPPED:
            self.state = DebateState.SPEAKER_2

    def finish_round(self) -> None:
        if self.state == DebateState.STOPPED:
            return
        self.state = DebateState.COMPLETE if self.debate_complete() else DebateState.WAIT_MODERATOR

    def record_candidate_turn(self, persona: str) -> None:
        if persona in self.turns_spoken:
            self.turns_spoken[persona] += 1
        if self.debate_complete():
            self.state = DebateState.COMPLETE

    def turn_available(self, persona: str) -> bool:
        return self.turns_spoken.get(persona, self.max_turns_per_persona) < self.max_turns_per_persona

    def _respect_turn_limits(self, first: str, second: str) -> tuple[str, str]:
        if self.turn_available(first):
            return first, second
        if self.turn_available(second):
            return second, first
        return first, second

    @staticmethod
    def choose_first_speaker(prompt: str) -> str:
        text = " ".join((prompt or "").strip().lower().split())
        if not text:
            return "trump"

        directive_patterns = (
            (r"\b(first|start|starts|begin|begins)\s+(with\s+)?(mr\.?\s+)?(president\s+)?(biden|joe)\b", "biden"),
            (r"\b(first|start|starts|begin|begins)\s+(with\s+)?(mr\.?\s+)?(president\s+)?(trump|donald)\b", "trump"),
            (r"\b(biden|joe)\s+(goes\s+)?(first|start|starts|begin|begins)\b", "biden"),
            (r"\b(trump|donald)\s+(goes\s+)?(first|start|starts|begin|begins)\b", "trump"),
        )
        for pattern, persona in directive_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return persona

        explicit_start = re.match(
            r"^(hey\s+)?((mr|president)\.?\s+)?(trump|donald|biden|joe)\b",
            text,
            flags=re.IGNORECASE,
        )
        if explicit_start:
            starter = explicit_start.group(4).lower()
            return "biden" if starter in {"biden", "joe"} else "trump"

        trump_patterns = (
            r"\bmr\.?\s+trump\b",
            r"\bpresident\s+trump\b",
            r"\bdonald\b",
            r"\btrump\b",
        )
        biden_patterns = (
            r"\bmr\.?\s+biden\b",
            r"\bpresident\s+biden\b",
            r"\bjoe\b",
            r"\bbiden\b",
        )

        trump_idx = DebateOrchestrator._first_pattern_match_index(text, trump_patterns)
        biden_idx = DebateOrchestrator._first_pattern_match_index(text, biden_patterns)

        if trump_idx is None and biden_idx is None:
            return "trump"
        if trump_idx is None:
            return "biden"
        if biden_idx is None:
            return "trump"
        return "trump" if trump_idx <= biden_idx else "biden"

    @staticmethod
    def _first_pattern_match_index(text: str, patterns: tuple[str, ...]) -> int | None:
        hit_indexes: list[int] = []
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                hit_indexes.append(match.start())
        return min(hit_indexes) if hit_indexes else None
