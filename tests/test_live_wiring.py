"""build_live_call and make_live_call: the stack shape, with fakes only. No network."""

from pathlib import Path

import pytest

from natter import audio_cache, live_wiring
from natter.audio_cache import CachedSpeech
from natter.live_wiring import build_live_call, make_live_call
from natter.providers.errors import MissingKeyError
from natter.providers.fakes import FakeExtractor, FakePersona, FakeSpeech
from natter.schema import Dossier
from natter.speech_budget import BudgetedSpeech
from natter.throttle import ThrottledSpeech
from tests.live_fakes import LINES


def build(tmp_path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    persona = kwargs.pop("persona", FakePersona(lines=["Oh hello dear."]))
    return build_live_call(
        persona,  # type: ignore[arg-type]
        FakeExtractor(Dossier()),
        kwargs.pop("speech", FakeSpeech()),  # type: ignore[arg-type]
        tmp_path / "audio",
        throttle_gap_s=0,  # no sleeping in tests
        **kwargs,  # type: ignore[arg-type]
    )


def test_budget_is_the_one_inside_the_cache(tmp_path: Path) -> None:
    call = build(tmp_path)
    assert isinstance(call.speech, CachedSpeech)
    assert call.budget is call.speech.inner  # same object, so the count is the real count
    assert isinstance(call.budget, BudgetedSpeech)
    assert isinstance(call.budget.inner, ThrottledSpeech)


def test_repeated_line_costs_one_request(tmp_path: Path) -> None:
    speech = FakeSpeech()
    call = build(tmp_path, speech=speech)
    call.say(LINES[0])
    second = call.say(LINES[1])  # same persona line, so the cache answers
    assert second.audio is not None
    assert second.speech_requests_used == 1
    assert len(speech.texts) == 1


def test_speech_cap_is_passed_through(tmp_path: Path) -> None:
    call = build(tmp_path, speech_cap=0)
    assert call.budget is not None and call.budget.max_requests == 0
    assert call.say(LINES[0]).notes == ["speech budget used up"]


def test_missing_keys_raise_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(MissingKeyError):
        make_live_call()


def test_make_live_call_uses_the_three_providers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Provider classes are swapped for fakes, so nothing is built that could reach the network."""
    persona, extractor = FakePersona(), FakeExtractor(Dossier())
    monkeypatch.setattr(live_wiring, "ClaudeExtractor", lambda: extractor)
    monkeypatch.setattr(live_wiring, "GroqPersona", lambda: persona)
    monkeypatch.setattr(live_wiring, "GroqSpeech", lambda: FakeSpeech())
    call = make_live_call(tmp_path / "audio", speech_cap=3)
    assert isinstance(call.speech, CachedSpeech) and call.budget is call.speech.inner
    assert call.budget is not None and call.budget.max_requests == 3
    assert call.persona is persona and call.extractor is extractor  # not swapped
    assert call.say(LINES[0]).audio is not None


# ---- the live audio folder must never fill up and silence the replies


def test_a_full_live_audio_folder_still_gives_every_reply_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = FakeSpeech().speak("x")
    monkeypatch.setattr(audio_cache, "MAX_FOLDER_BYTES", len(wav) * 2)  # room for two clips
    persona = FakePersona(lines=["Oh hello dear.", "Who is it?", "Oh my.", "Go on then."])
    call = build(tmp_path, persona=persona)
    replies = [call.say(line) for line in LINES + ["One more."]]
    assert all(r.audio is not None for r in replies)  # the 3rd and 4th used to be text only
    assert all(r.notes == [] for r in replies)
    assert len(list((tmp_path / "audio").glob("*.wav"))) == 2  # the oldest were removed


def test_audio_that_cannot_be_saved_is_still_played_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call = build(tmp_path)
    assert isinstance(call.speech, CachedSpeech)

    def broken_store(key: str, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(call.speech.cache, "store", broken_store)
    reply = call.say(LINES[0])
    assert reply.audio is not None  # made and paid for, so it is not thrown away
    assert reply.notes == ["audio not saved: OSError"]  # type only, never the OS message
    assert reply.speech_requests_used == 1


def test_make_live_call_without_speech_never_builds_the_speech_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_speech_allowed() -> FakeSpeech:
        raise AssertionError("GroqSpeech must not be built")

    monkeypatch.setattr(live_wiring, "ClaudeExtractor", lambda: FakeExtractor(Dossier()))
    monkeypatch.setattr(live_wiring, "GroqPersona", lambda: FakePersona())
    monkeypatch.setattr(live_wiring, "GroqSpeech", no_speech_allowed)
    call = make_live_call(tmp_path / "audio", speech=False)
    assert call.speech is None and call.budget is None
    reply = call.say(LINES[0])
    assert reply.audio is None and reply.notes == []
    assert not (tmp_path / "audio").exists()  # no audio folder is even made
