"""Tests for the session loop."""

import json
from pathlib import Path

import pytest

from natter.picker import Goal
from natter.providers.fakes import FakeExtractor, FakePersona
from natter.schema import (
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    PaymentMethod,
    Sourced,
    Stage,
    Turn,
)
from natter.session import run_session

SCENARIO = Path(__file__).parent.parent / "scenarios" / "bank-fraud-01"
LINES = ["first line here", "second line here", "third line here"]


class ScriptedExtractor:
    """Returns dossiers[i] on call i (the last one repeats) and records transcripts."""

    name = "scripted-extractor"

    def __init__(self, dossiers: list[Dossier]) -> None:
        self.dossiers = dossiers
        self.seen: list[list[Turn]] = []

    def extract(self, transcript: list[Turn]) -> Dossier:
        self.seen.append(list(transcript))  # copy: the session keeps appending
        position = min(len(self.seen) - 1, len(self.dossiers) - 1)
        return self.dossiers[position].model_copy(deep=True)


class RecordingPersona:
    """Always says "ok dear" and records what it was given."""

    name = "recording-persona"

    def __init__(self) -> None:
        self.calls: list[tuple[list[Turn], Goal | None]] = []

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        self.calls.append((list(transcript), goal))  # copy: the session keeps appending
        return "ok dear"


def stage_dossier(stage: Stage, turn: int, quote: str) -> Dossier:
    """A dossier holding only a stage backed by the given quote."""
    evidence = Evidence(turn=turn, quote=quote, confidence=0.9)
    return Dossier(stage=Sourced[Stage](value=stage, evidence=evidence))


def test_turns_alternate_and_are_indexed() -> None:
    """Three lines give six turns, scammer on even indexes, persona on odd."""
    result = run_session(LINES, RecordingPersona(), ScriptedExtractor([Dossier()]), 100)
    assert [t.index for t in result.transcript] == [0, 1, 2, 3, 4, 5]
    assert [t.speaker for t in result.transcript] == ["scammer", "persona"] * 3
    assert [t.text for t in result.transcript[::2]] == LINES


def test_max_turns_caps_total_turns() -> None:
    """The cap counts scammer and persona turns together."""
    for cap, expected in [(0, 0), (1, 1), (4, 4), (5, 5)]:
        persona = RecordingPersona()
        result = run_session(LINES, persona, ScriptedExtractor([Dossier()]), cap)
        assert len(result.transcript) == expected
        if cap == 5:
            assert result.transcript[-1].speaker == "scammer"
            assert len(persona.calls) == 2


def test_extractor_sees_transcript_ending_with_scammer_turn() -> None:
    """Each extract call sees the transcript up to and including the new scammer line."""
    extractor = ScriptedExtractor([Dossier()])
    run_session(LINES, RecordingPersona(), extractor, 100)
    assert [len(seen) for seen in extractor.seen] == [1, 3, 5]
    assert all(seen[-1].speaker == "scammer" for seen in extractor.seen)


def test_bad_quote_is_rejected_and_dropped() -> None:
    """An identifier whose quote is not in the cited turn is dropped and logged."""
    bad = Identifier(
        kind=IdentifierKind.ALIAS,
        value="Nobody",
        evidence=Evidence(turn=0, quote="not in the turn", confidence=0.9),
    )
    result = run_session(
        LINES[:1], RecordingPersona(), ScriptedExtractor([Dossier(identifiers=[bad])]), 100
    )
    assert result.dossier.identifiers == []
    assert [r.reason for r in result.rejections] == ["quote not found in cited turn"]


def test_stage_never_goes_backwards() -> None:
    """Pressure is accepted, then hook is rejected twice, and the carried stage is used."""
    proposals = [
        stage_dossier(Stage.PRESSURE, 0, "first line"),
        stage_dossier(Stage.HOOK, 2, "second line"),
        stage_dossier(Stage.HOOK, 4, "third line"),
    ]
    result = run_session(LINES, RecordingPersona(), ScriptedExtractor(proposals), 100)
    assert result.dossier.stage is None  # the final dossier is the latest checked one
    assert [(r.field, r.reason) for r in result.rejections] == [
        ("stage", "stage moved backwards"),
        ("stage", "stage moved backwards"),
    ]


def test_goal_matches_next_goal_of_checked_dossier() -> None:
    """The persona is steered by the checked dossier, not the raw proposal."""
    bad_phone = Identifier(
        kind=IdentifierKind.PHONE,
        value="07700 900000",
        evidence=Evidence(turn=0, quote="not in the turn", confidence=0.9),
    )
    proposal = Dossier(identifiers=[bad_phone])  # raw proposal would give PAYMENT_METHOD
    persona = RecordingPersona()
    run_session(LINES[:1], persona, ScriptedExtractor([proposal]), 100)
    assert [goal for _, goal in persona.calls] == [Goal.CALLBACK_NUMBER]


def test_inputs_not_mutated() -> None:
    """The scammer lines and the extractor's preset dossier are unchanged."""
    lines = list(LINES)
    evidence = Evidence(turn=0, quote="first line", confidence=0.9)
    preset = Dossier(
        payment_method=Sourced[PaymentMethod](value=PaymentMethod.CRYPTO, evidence=evidence)
    )
    before = preset.model_copy(deep=True)
    run_session(lines, RecordingPersona(), ScriptedExtractor([preset]), 100)
    assert lines == LINES
    assert preset == before


JUNK = Turn(index=99, speaker="scammer", text="junk turn")


class JunkPersona:
    """Appends a junk turn to the list it is given, then replies."""

    name = "junk-persona"

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        transcript.append(JUNK)  # simulates a provider that mutates its input
        return "ok dear"


class JunkExtractor:
    """Appends a junk turn to the list it is given, then proposes nothing."""

    name = "junk-extractor"

    def extract(self, transcript: list[Turn]) -> Dossier:
        transcript.append(JUNK)  # simulates a provider that mutates its input
        return Dossier()


def test_providers_get_copies_of_transcript() -> None:
    """Providers that append to their transcript cannot change the real one."""
    result = run_session(LINES, JunkPersona(), JunkExtractor(), 100)
    assert [t.index for t in result.transcript] == [0, 1, 2, 3, 4, 5]
    assert JUNK not in result.transcript


def test_bank_fraud_full_run() -> None:
    """The real script gives 20 turns and, at the end, exactly the expected dossier."""
    script = json.loads((SCENARIO / "script.json").read_text(encoding="utf-8"))
    lines = [item["text"] for item in script["scammer_turns"]]
    expected = Dossier.model_validate_json((SCENARIO / "expected.json").read_text(encoding="utf-8"))
    result = run_session(lines, FakePersona(), FakeExtractor(expected), 100)
    assert len(result.transcript) == 20
    assert result.dossier == expected


FAKE_PHONE = "call me on 0900 999999"
FAKE_PHONE_ID = Identifier(
    kind=IdentifierKind.PHONE,
    value="0900 999999",
    evidence=Evidence(turn=0, quote="0900 999999", confidence=0.9),
)


class ForgingExtractor:
    """Rewrites turn 0 in place, then cites the forged text as evidence."""

    name = "forging-extractor"

    def extract(self, transcript: list[Turn]) -> Dossier:
        transcript[0].text = FAKE_PHONE  # edits the Turn object, not the list
        return Dossier(identifiers=[FAKE_PHONE_ID])


class ForgingPersona:
    """Rewrites turn 0 in place, then replies."""

    name = "forging-persona"

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        transcript[0].text = FAKE_PHONE  # edits the Turn object, not the list
        return "ok dear"


def test_extractor_cannot_edit_a_turn_in_place() -> None:
    """An extractor that rewrites turn 0 changes nothing real, and its forged quote fails."""
    result = run_session(LINES, RecordingPersona(), ForgingExtractor(), 100)
    assert [t.text for t in result.transcript[::2]] == LINES
    assert result.dossier.identifiers == []
    assert "quote not found in cited turn" in [r.reason for r in result.rejections]


def test_persona_cannot_edit_a_turn_in_place() -> None:
    """A persona that rewrites turn 0 changes nothing real."""
    result = run_session(LINES, ForgingPersona(), ScriptedExtractor([Dossier()]), 100)
    assert [t.text for t in result.transcript[::2]] == LINES


@pytest.mark.parametrize("cap", [2.5, True, -1])
def test_bad_max_turns_raise(cap: object) -> None:
    """A cap that is not a whole number zero or more is refused."""
    with pytest.raises(ValueError):
        run_session(LINES, RecordingPersona(), ScriptedExtractor([Dossier()]), cap)  # type: ignore[arg-type]


class CountingPersona:
    """Replies "reply 1", "reply 2", ... so each reply can be told apart."""

    name = "counting-persona"

    def __init__(self) -> None:
        self.count = 0

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        self.count += 1
        return f"reply {self.count}"


def test_each_persona_reply_lands_in_order() -> None:
    """The persona's own words, not a placeholder, fill the odd turns in order."""
    result = run_session(LINES, CountingPersona(), ScriptedExtractor([Dossier()]), 100)
    assert [t.text for t in result.transcript[1::2]] == ["reply 1", "reply 2", "reply 3"]


def test_goal_follows_the_current_checked_dossier() -> None:
    """The goal moves on as each turn's checked dossier fills up."""
    lines = ["call 07700 900482 now", "pay by bank transfer", "this is Kestrel Bank"]
    phone = Identifier(
        kind=IdentifierKind.PHONE,
        value="07700 900482",
        evidence=Evidence(turn=0, quote="07700 900482", confidence=0.9),
    )
    payment = Sourced[PaymentMethod](
        value=PaymentMethod.BANK_TRANSFER,
        evidence=Evidence(turn=2, quote="bank transfer", confidence=0.9),
    )
    proposals = [
        Dossier(),  # call 1: nothing known yet
        Dossier(identifiers=[phone]),  # call 2: phone known
        Dossier(identifiers=[phone], payment_method=payment),  # call 3: payment known too
    ]
    persona = RecordingPersona()
    run_session(lines, persona, ScriptedExtractor(proposals), 100)
    assert [goal for _, goal in persona.calls] == [
        Goal.CALLBACK_NUMBER,
        Goal.PAYMENT_METHOD,
        Goal.CLAIMED_ORGANISATION,
    ]


def test_stage_moves_forward_then_cannot_drop_back() -> None:
    """HOOK then CLOSING are accepted, then PAYMENT_ASK is rejected as backwards."""
    proposals = [
        stage_dossier(Stage.HOOK, 0, "first line"),
        stage_dossier(Stage.CLOSING, 2, "second line"),
        stage_dossier(Stage.PAYMENT_ASK, 4, "third line"),
    ]
    result = run_session(LINES, RecordingPersona(), ScriptedExtractor(proposals), 100)
    assert [(r.field, r.reason) for r in result.rejections] == [
        ("stage", "stage moved backwards"),
    ]


def test_two_rejections_in_one_turn_are_both_kept() -> None:
    """Every drop from a single turn is reported, not just the first."""
    bad = Evidence(turn=0, quote="not in the turn", confidence=0.9)
    proposal = Dossier(
        identifiers=[
            Identifier(kind=IdentifierKind.ALIAS, value="A", evidence=bad),
            Identifier(kind=IdentifierKind.ALIAS, value="B", evidence=bad),
        ]
    )
    result = run_session(LINES[:1], RecordingPersona(), ScriptedExtractor([proposal]), 100)
    assert [r.field for r in result.rejections] == ["identifiers[0]", "identifiers[1]"]


def test_persona_sees_the_newest_scammer_line() -> None:
    """Each persona call gets the transcript ending with the line it is answering."""
    persona = RecordingPersona()
    run_session(LINES, persona, ScriptedExtractor([Dossier()]), 100)
    assert [len(seen) for seen, _ in persona.calls] == [1, 3, 5]
    assert [seen[-1].text for seen, _ in persona.calls] == LINES
    assert all(seen[-1].speaker == "scammer" for seen, _ in persona.calls)


def test_each_rejection_records_its_scammer_turn() -> None:
    """rejection_turns[i] is the scammer turn whose extraction dropped rejections[i]."""
    bad = Evidence(turn=0, quote="not in the turn", confidence=0.9)
    proposal = Dossier(
        identifiers=[
            Identifier(kind=IdentifierKind.ALIAS, value="A", evidence=bad),
            Identifier(kind=IdentifierKind.ALIAS, value="B", evidence=bad),
        ]
    )
    # The same bad proposal on all three scammer turns (indexes 0, 2, 4): two drops each
    result = run_session(LINES, RecordingPersona(), ScriptedExtractor([proposal]), 100)
    assert len(result.rejection_turns) == len(result.rejections) == 6
    assert result.rejection_turns == [0, 0, 2, 2, 4, 4]
