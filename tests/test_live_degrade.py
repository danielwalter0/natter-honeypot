"""LiveCall when a provider misbehaves: persona, speech and extraction degrade, never raise."""

from pathlib import Path

import pytest

from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.providers.errors import PersonaError
from natter.providers.fakes import FakePersona, FakeSpeech
from natter.providers.reply_tidy import SAFE_STALL
from natter.speech_budget import BudgetedSpeech
from tests.live_fakes import (
    HOSTILE_TEXT,
    LINES,
    OddPersona,
    RaisingExtractor,
    RaisingPersona,
    RaisingSpeech,
    make_call,
)


def test_persona_failure_uses_safe_stall() -> None:
    call = make_call(persona=RaisingPersona())
    reply = call.say(LINES[0])
    assert reply.text == SAFE_STALL
    assert reply.goal is None and call.state.previous_goal is None
    assert reply.notes[0].startswith("persona failed")
    assert call.say(LINES[1]).text == SAFE_STALL  # the call carries on


def test_persona_inventing_digits_is_replaced() -> None:
    persona = FakePersona(lines=["Is your card 4929 1234 5678 9012?"])
    assert make_call(persona=persona).say(LINES[0]).text == SAFE_STALL


@pytest.mark.parametrize("value", [None, 12345, "x" * 3000, "   "])
def test_odd_persona_output_uses_safe_stall(value: object) -> None:
    reply = make_call(persona=OddPersona(value)).say(LINES[0])
    assert reply.text == SAFE_STALL
    assert reply.notes[0].startswith("persona failed")


@pytest.mark.parametrize("value", [" , ", "[warm]", "[sighs]"])
def test_unspeakable_persona_output_uses_safe_stall(value: str) -> None:
    speech = FakeSpeech()
    reply = make_call(persona=OddPersona(value), speech=speech).say(LINES[0])
    assert reply.text == SAFE_STALL
    assert reply.notes[0].startswith("persona failed")
    assert reply.audio is not None and len(speech.texts) == 1  # the stall is voiced


def test_persona_lone_surrogate_uses_safe_stall_and_call_goes_on() -> None:
    call = make_call(persona=FakePersona(lines=["Oh hello \ud800 dear.", "Oh hello dear."]))
    first = call.say(LINES[0])
    assert first.text == SAFE_STALL
    assert first.notes[0].startswith("persona failed")
    assert [t.speaker for t in call.state.transcript] == ["scammer", "persona"]
    second = call.say(LINES[1])
    assert second.text == "Oh hello dear."
    assert [t.speaker for t in call.state.transcript] == ["scammer", "persona"] * 2


def test_speech_failure_keeps_text() -> None:
    reply = make_call(speech=RaisingSpeech()).say(LINES[0])
    assert reply.text is not None and reply.audio is None
    assert reply.notes[0].startswith("speech failed")


def test_budget_used_up_keeps_text() -> None:
    budget = BudgetedSpeech(FakeSpeech(), 0)
    reply = make_call(speech=budget, budget=budget).say(LINES[0])
    assert reply.text is not None and reply.audio is None
    assert reply.notes == ["speech budget used up"]
    assert reply.speech_requests_used == 0


def test_cache_hit_does_not_use_budget(tmp_path: Path) -> None:
    budget = BudgetedSpeech(FakeSpeech(), 15)
    speech = CachedSpeech(budget, AudioCache(tmp_path, "record"), speech_key)
    persona = FakePersona(lines=["Oh hello dear."])
    call = make_call(persona=persona, speech=speech, budget=budget)
    call.say(LINES[0])
    second = call.say(LINES[1])
    assert second.speech_requests_used == 1
    assert second.audio is not None


def test_notes_never_hold_a_key() -> None:
    reply = make_call(persona=RaisingPersona(), speech=RaisingSpeech()).say(LINES[0])
    assert len(reply.notes) == 2
    assert "sk-test-HOSTILE_TEXT" not in " ".join(reply.notes)


def test_notes_hide_text_of_foreign_errors() -> None:
    """ValueError (which may come from an SDK or a hostile line) shows its type only."""
    bad = ValueError(HOSTILE_TEXT)
    call = make_call(
        extractor=RaisingExtractor(bad), persona=RaisingPersona(bad), speech=RaisingSpeech(bad)
    )
    notes = " ".join(call.say(LINES[0]).notes)
    assert "extraction failed: ValueError" in notes
    assert "persona failed: ValueError" in notes
    assert "speech failed: ValueError" in notes
    assert "sk-test-HOSTILE_TEXT" not in notes and "ignore previous" not in notes


def test_notes_show_our_own_error_message() -> None:
    reply = make_call(persona=RaisingPersona(PersonaError("reply did not finish"))).say(LINES[0])
    assert reply.notes[0] == "persona failed: PersonaError: reply did not finish"


# ---- speech switched off, and the plain note for a speech rate limit


class RateLimitError(Exception):
    """Stands in for the SDK's 429 error: same name and status, hostile text inside."""

    status_code = 429


def test_no_speech_makes_no_request_and_adds_no_note() -> None:
    call = make_call(speech=None)
    reply = call.say(LINES[0])
    assert reply.text  # she still answers in text
    assert reply.audio is None
    assert reply.notes == []
    assert reply.speech_requests_used == 0


def test_a_speech_rate_limit_gets_a_plain_note_and_the_detail_goes_to_the_terminal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call = make_call(speech=RaisingSpeech(RateLimitError(HOSTILE_TEXT)))
    reply = call.say(LINES[0])
    assert reply.notes == ["Speech limit reached, showing text only."]
    out = capsys.readouterr().out
    assert "speech failed: RateLimitError status 429" in out  # technical detail, terminal only
    assert "sk-test-HOSTILE_TEXT" not in out and "ignore previous" not in out
