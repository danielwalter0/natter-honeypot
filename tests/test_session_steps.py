"""Tests for the four session step functions. No providers are involved."""

from natter.picker import Goal, next_goal
from natter.schema import (
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    Money,
    PaymentMethod,
    Sourced,
    Stage,
)
from natter.session import (
    SessionState,
    add_persona_reply,
    add_scammer_line,
    apply_extraction,
    choose_goal,
)


def full_dossier() -> Dossier:
    """A dossier holding every field the picker asks for, so next_goal has nothing left."""
    ev = Evidence(turn=0, quote="any quote", confidence=0.9)  # never checked here
    return Dossier(
        claimed_organisation=Sourced[str](value="Some Bank", evidence=ev),
        payment_method=Sourced[PaymentMethod](value=PaymentMethod.BANK_TRANSFER, evidence=ev),
        amount=Sourced[Money](value=Money(amount=100.0, currency="GBP"), evidence=ev),
        identifiers=[
            Identifier(kind=IdentifierKind.PHONE, value="0000", evidence=ev),
            Identifier(kind=IdentifierKind.CASE_REFERENCE, value="REF", evidence=ev),
        ],
    )


def state_with_scammer_line(text: str = "first line") -> SessionState:
    """A session holding one scammer turn, ready for an extraction."""
    state = SessionState()
    add_scammer_line(state, text)
    return state


def stage_dossier(stage: Stage, turn: int, quote: str) -> Dossier:
    """A dossier holding only a stage backed by the given quote."""
    evidence = Evidence(turn=turn, quote=quote, confidence=0.9)
    return Dossier(stage=Sourced[Stage](value=stage, evidence=evidence))


def alias(value: str, quote: str, turn: int = 0) -> Identifier:
    """An alias identifier citing the given quote in the given turn."""
    return Identifier(
        kind=IdentifierKind.ALIAS,
        value=value,
        evidence=Evidence(turn=turn, quote=quote, confidence=0.9),
    )


def test_new_state_is_empty() -> None:
    state = SessionState()
    assert state.transcript == []
    assert state.dossier == Dossier()
    assert state.previous_stage is None
    assert state.previous_goal is None
    assert state.rejections == []
    assert state.rejection_turns == []
    assert state.goals == []


def test_two_new_states_do_not_share_lists() -> None:
    a, b = SessionState(), SessionState()
    add_scammer_line(a, "hello")
    assert b.transcript == []


def test_add_scammer_line_indexes_from_zero() -> None:
    state = SessionState()
    add_scammer_line(state, "one")
    add_scammer_line(state, "two")
    assert [(t.index, t.speaker, t.text) for t in state.transcript] == [
        (0, "scammer", "one"),
        (1, "scammer", "two"),
    ]


def test_apply_extraction_keeps_a_good_fact() -> None:
    state = state_with_scammer_line("this is Kestrel Bank")
    good = Dossier(identifiers=[alias("Kestrel", "Kestrel")])
    dropped = apply_extraction(state, good)
    assert dropped == []
    assert state.dossier == good
    assert state.rejections == []
    assert state.rejection_turns == []


def test_apply_extraction_drops_a_bad_quote_and_returns_it() -> None:
    state = state_with_scammer_line()
    dropped = apply_extraction(state, Dossier(identifiers=[alias("Nobody", "not in the turn")]))
    assert [r.reason for r in dropped] == ["quote not found in cited turn"]
    assert state.dossier.identifiers == []
    assert state.rejections == dropped


def test_apply_extraction_returns_only_this_turns_drops() -> None:
    state = state_with_scammer_line()
    bad = Dossier(identifiers=[alias("Nobody", "not in the turn")])
    first = apply_extraction(state, bad)
    second = apply_extraction(state, bad)
    assert len(first) == len(second) == 1
    assert len(state.rejections) == 2  # the state keeps both, the return value one


def test_apply_extraction_records_the_scammer_turn_of_each_drop() -> None:
    state = state_with_scammer_line()
    bad = Dossier(identifiers=[alias("A", "not in the turn"), alias("B", "not in the turn")])
    apply_extraction(state, bad)
    state.transcript.append(
        state.transcript[0].model_copy(update={"index": 1, "speaker": "persona"})
    )
    add_scammer_line(state, "third")  # scammer turn is now index 2
    apply_extraction(state, bad)
    assert state.rejection_turns == [0, 0, 2, 2]


def test_apply_extraction_never_moves_stage_backwards() -> None:
    state = state_with_scammer_line("first line")
    apply_extraction(state, stage_dossier(Stage.PRESSURE, 0, "first line"))
    assert state.previous_stage == Stage.PRESSURE
    dropped = apply_extraction(state, stage_dossier(Stage.HOOK, 0, "first line"))
    assert [(r.field, r.reason) for r in dropped] == [("stage", "stage moved backwards")]
    assert state.dossier.stage is None  # the dossier is the latest checked one
    assert state.previous_stage == Stage.PRESSURE  # a drop does not reset it


def test_choose_goal_returns_next_goal() -> None:
    state = SessionState()
    assert choose_goal(state) == next_goal(state.dossier) == Goal.CALLBACK_NUMBER


def test_choose_goal_returns_none_when_same_as_previous_goal() -> None:
    state = SessionState(previous_goal=Goal.CALLBACK_NUMBER)
    assert next_goal(state.dossier) == Goal.CALLBACK_NUMBER
    assert choose_goal(state) is None


def test_choose_goal_returns_a_different_goal_even_if_one_was_given_before() -> None:
    state = SessionState(previous_goal=Goal.PAYMENT_METHOD)
    assert choose_goal(state) == Goal.CALLBACK_NUMBER


def test_choose_goal_returns_none_when_nothing_left_to_ask() -> None:
    """A complete dossier has no next goal; that must give None, not an error."""
    full = full_dossier()
    state = SessionState(dossier=full)
    assert next_goal(full) is None  # guards the premise of this test
    assert choose_goal(state) is None


def test_choose_goal_changes_nothing_in_state() -> None:
    state = state_with_scammer_line()
    state.previous_goal = Goal.CALLBACK_NUMBER
    state.goals.append(Goal.CALLBACK_NUMBER)
    choose_goal(state)
    assert state.previous_goal == Goal.CALLBACK_NUMBER
    assert state.goals == [Goal.CALLBACK_NUMBER]
    assert len(state.transcript) == 1


def test_add_persona_reply_appends_a_persona_turn() -> None:
    state = state_with_scammer_line()
    add_persona_reply(state, Goal.CALLBACK_NUMBER, "oh hello dear")
    turn = state.transcript[-1]
    assert (turn.index, turn.speaker, turn.text) == (1, "persona", "oh hello dear")
    assert len(state.transcript) == 2


def test_add_persona_reply_appends_goal_and_sets_previous_goal() -> None:
    state = state_with_scammer_line()
    add_persona_reply(state, Goal.CALLBACK_NUMBER, "oh hello dear")
    assert state.goals == [Goal.CALLBACK_NUMBER]
    assert state.previous_goal == Goal.CALLBACK_NUMBER


def test_add_persona_reply_with_none_goal_resets_previous_goal() -> None:
    state = state_with_scammer_line()
    add_persona_reply(state, Goal.CALLBACK_NUMBER, "first")
    add_scammer_line(state, "second")
    add_persona_reply(state, None, "a stall")  # a caller that fell back to a stall
    assert state.goals == [Goal.CALLBACK_NUMBER, None]
    assert state.previous_goal is None
    assert state.transcript[-1].index == 3
