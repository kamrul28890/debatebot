from pathlib import Path

from src.cache.deterministic import MAX_WORDS_PER_TURN, build_script, script_fingerprint


def test_deterministic_turn_lengths_capped() -> None:
    script = build_script()
    for persona in ("trump", "biden", "siskind"):
        turns = script.get(persona, [])
        assert turns, f"Expected deterministic turns for {persona}"
        assert all(len(turn.split()) <= MAX_WORDS_PER_TURN for turn in turns)


def test_deterministic_fingerprint_stable() -> None:
    script_a = build_script()
    script_b = build_script()
    assert script_fingerprint(script_a) == script_fingerprint(script_b)
