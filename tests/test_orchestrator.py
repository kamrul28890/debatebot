from src.core import DebateOrchestrator, DebateState


def test_user_routing_defaults_to_trump_when_not_addressed() -> None:
    orchestrator = DebateOrchestrator(max_turns_per_persona=8)
    plan = orchestrator.next_user_round("What's your economic plan?")
    assert plan.first_speaker == "trump"
    assert plan.second_speaker == "biden"


def test_user_routing_selects_addressed_candidate() -> None:
    orchestrator = DebateOrchestrator(max_turns_per_persona=8)
    plan = orchestrator.next_user_round("Mr. Biden, are we ready for this?")
    assert plan.first_speaker == "biden"
    assert plan.second_speaker == "trump"


def test_state_machine_progression_and_completion() -> None:
    orchestrator = DebateOrchestrator(max_turns_per_persona=1)

    plan = orchestrator.next_user_round("Mr. Trump, first response")
    assert orchestrator.state == DebateState.SPEAKER_1

    orchestrator.record_candidate_turn(plan.first_speaker)
    orchestrator.begin_second_speaker()
    assert orchestrator.state == DebateState.SPEAKER_2

    orchestrator.record_candidate_turn(plan.second_speaker)
    orchestrator.finish_round()
    assert orchestrator.state == DebateState.COMPLETE
    assert not orchestrator.can_continue()


def test_siskind_round_alternates_starter() -> None:
    orchestrator = DebateOrchestrator(max_turns_per_persona=8)
    first = orchestrator.next_siskind_round("Topic A").first_speaker
    second = orchestrator.next_siskind_round("Topic B").first_speaker
    assert first != second
