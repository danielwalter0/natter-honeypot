"""Tests for LiveCall.say: happy path, parity with run_session, bad lines, caps."""

import pytest

from natter.audio_cache import is_wav
from natter.live import MAX_LINE_CHARS
from natter.providers.fakes import FakeExtractor, FakePersona, FakeSpeech
from natter.schema import Dossier, Evidence, Sourced, Stage
from natter.session import run_session
from natter.speech_text import DIRECTION, prepare_speech_text
from tests.live_fakes import BAD, LINES, PHONE, make_call


class FirstTurnBadExtractor:
    """Proposes a bad quote on the first call only."""

    name = "first-bad"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, transcript: list) -> Dossier:  # type: ignore[type-arg]
        self.calls += 1
        return Dossier(identifiers=[PHONE, BAD] if self.calls == 1 else [PHONE])


def stage_and_bad_fact() -> Dossier:
    """A good stage plus one fact with a bad quote, so every turn has a rejection."""
    stage = Sourced[Stage](
        value=Stage.HOOK, evidence=Evidence(turn=0, quote="07700 900482", confidence=0.9)
    )
    return Dossier(stage=stage, identifiers=[PHONE, BAD])


def test_matches_run_session() -> None:
    """The same (unpadded) lines give the same transcript, dossier, drops and goals."""
    call = make_call(extractor=FakeExtractor(stage_and_bad_fact()))
    for line in LINES:
        call.say(line)
    expected = run_session(LINES, FakePersona(), FakeExtractor(stage_and_bad_fact()), 100)
    assert call.state.rejections  # the comparison is not vacuous
    assert call.state.transcript == expected.transcript
    assert call.state.dossier == expected.dossier
    assert call.state.rejections == expected.rejections
    assert call.state.rejection_turns == expected.rejection_turns
    assert call.state.goals == expected.goals


def test_reply_has_text_audio_goal_dossier() -> None:
    speech = FakeSpeech()
    persona = FakePersona(lines=["Oh hello dear."])
    reply = make_call(persona=persona, speech=speech).say(LINES[0])
    assert reply.text == "Oh hello dear."
    assert reply.audio is not None and is_wav(reply.audio)
    assert reply.goal is not None
    assert reply.dossier.identifiers[0].value == "07700 900482"
    assert speech.texts == [prepare_speech_text("Oh hello dear.", DIRECTION)]
    assert not reply.ended and reply.notes == []


def test_reply_dossier_is_a_copy() -> None:
    call = make_call()
    reply = call.say(LINES[0])
    reply.dossier.identifiers.clear()  # a caller editing its copy
    assert len(call.state.dossier.identifiers) == 1


def test_rejections_are_this_turn_only() -> None:
    call = make_call(extractor=FirstTurnBadExtractor())
    first = call.say(LINES[0])
    second = call.say(LINES[1])
    assert len(first.rejections) == 1
    assert second.rejections == []


@pytest.mark.parametrize(
    "line", ["", "   \n", None, 42, "x" * (MAX_LINE_CHARS + 1), "\ud800 hello"]
)
def test_bad_line_adds_no_turn(line: object) -> None:
    call = make_call()
    reply = call.say(line)  # type: ignore[arg-type]
    assert reply.text is None and not reply.ended
    assert reply.notes[0].startswith("line rejected")
    assert call.state.transcript == []


def test_lone_surrogate_line_note_and_call_goes_on() -> None:
    call = make_call()
    assert call.say("\ud800 hello").notes == ["line rejected: not valid text"]
    assert call.say(LINES[0]).text is not None


def test_turn_cap_ends_call_without_providers() -> None:
    persona = FakePersona()
    call = make_call(persona=persona, max_turns=1)
    first = call.say(LINES[0])
    assert first.text is None and first.ended
    assert [t.speaker for t in call.state.transcript] == ["scammer"]
    later = call.say(LINES[1])
    assert later.ended and later.text is None
    assert persona.position == 0  # no persona call at all


def test_reply_that_fills_the_turn_cap_is_marked_ended() -> None:
    persona = FakePersona()
    call = make_call(persona=persona, max_turns=2)
    reply = call.say(LINES[0])
    assert reply.text is not None and reply.ended
    calls_before = persona.position
    later = call.say(LINES[1])
    assert later.ended and later.text is None
    assert persona.position == calls_before  # no provider call


def test_time_cap_ends_call() -> None:
    times = iter([0.0, 5.0, 11.0, 12.0])  # start, first say, second say, spare
    call = make_call(max_seconds=10, clock=lambda: next(times))
    assert call.say(LINES[0]).text is not None
    late = call.say(LINES[1])
    assert late.ended and late.text is None and "time cap" in late.notes[0]
    assert call.say(LINES[2]).ended  # ended stays ended


def test_time_cap_boundary() -> None:
    """Exactly started + max_seconds ends the call; just below does not."""
    now = [100.0]
    call = make_call(max_seconds=10, clock=lambda: now[0])
    now[0] = 109.999
    assert not call.say(LINES[0]).ended
    now[0] = 110.0
    assert call.say(LINES[1]).ended


@pytest.mark.parametrize("bad", [-1, True, 1.5, "3", None])
def test_bad_int_caps_raise(bad: object) -> None:
    with pytest.raises(ValueError):
        make_call(max_turns=bad)
    with pytest.raises(ValueError):
        make_call(max_extractions=bad)


@pytest.mark.parametrize("bad", [0, -1, True, "5", None, float("nan")])
def test_bad_max_seconds_raises(bad: object) -> None:
    with pytest.raises(ValueError):
        make_call(max_seconds=bad)
