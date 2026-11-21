from pathlib import Path

import pytest

from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.audio_record import describe_error, missing, persona_lines, record
from natter.cache import CacheMiss
from natter.providers.errors import MissingKeyError, SpeechError
from natter.providers.fakes import FakeSpeech
from natter.schema import Turn


def turns(*persona_texts: str) -> list[Turn]:
    """A scammer turn before each persona turn."""
    out: list[Turn] = []
    for text in persona_texts:
        out.append(Turn(index=len(out), speaker="scammer", text="Send gift cards"))
        out.append(Turn(index=len(out), speaker="persona", text=text))
    return out


class FailsOnSecond(FakeSpeech):
    """Works once, then raises on the next call."""

    def speak(self, text: str) -> bytes:
        if len(self.texts) == 1:
            raise RuntimeError("boom")
        return super().speak(text)


def make(folder: Path, speech: FakeSpeech | None = None) -> CachedSpeech:
    """A recording CachedSpeech over a fake provider, with the real key builder."""
    return CachedSpeech(speech or FakeSpeech(), AudioCache(folder, "record"), speech_key)


def wavs(folder: Path) -> list[Path]:
    return list(folder.glob("*.wav"))


def test_only_persona_turns_are_voiced() -> None:
    assert persona_lines(turns("Hello dear", "Oh my")) == ["[warm] Hello dear", "[warm] Oh my"]


def test_long_reply_has_no_tag() -> None:
    text = "a" * 199
    assert persona_lines(turns(text)) == [text]


def test_first_run_calls_then_second_run_is_free(tmp_path: Path) -> None:
    lines = persona_lines(turns("one", "two", "three"))
    speech = FakeSpeech()
    cached = make(tmp_path, speech)
    assert record(lines, cached) == 3
    assert len(wavs(tmp_path)) == 3
    assert record(lines, cached) == 0
    assert len(speech.texts) == 3


def test_over_cap_raises_before_any_call(tmp_path: Path) -> None:
    lines = persona_lines(turns("one", "two", "three"))
    speech = FakeSpeech()
    with pytest.raises(ValueError):
        record(lines, make(tmp_path, speech), max_requests=2)
    assert speech.texts == []
    assert wavs(tmp_path) == []


def test_failure_keeps_stored_files_and_rerun_resumes(tmp_path: Path) -> None:
    lines = persona_lines(turns("one", "two", "three"))
    with pytest.raises(RuntimeError):
        record(lines, make(tmp_path, FailsOnSecond()))
    assert len(wavs(tmp_path)) == 1
    assert len(missing(lines, make(tmp_path))) == 2
    good = FakeSpeech()
    assert record(lines, make(tmp_path, good)) == 2
    assert good.texts == lines[1:]


def test_duplicates_spoken_once(tmp_path: Path) -> None:
    lines = persona_lines(turns("same", "same", "other"))
    speech = FakeSpeech()
    assert record(lines, make(tmp_path, speech)) == 2
    assert len(speech.texts) == 2


def test_missing_uses_speech_key(tmp_path: Path) -> None:
    cached = make(tmp_path)
    lines = ["[warm] hi"]
    assert missing(lines, cached) == lines
    record(lines, cached)
    assert cached.cache.path_for(speech_key("fake-speech", lines[0])).exists()
    assert missing(lines, cached) == []


def test_missing_and_speak_agree_on_the_key(tmp_path: Path) -> None:
    lines = persona_lines(turns("one", "two"))
    cached = make(tmp_path)
    record(lines, cached)
    assert missing(lines, cached) == []  # the files speak() wrote are the ones missing() looks for


@pytest.mark.parametrize("bad", [b"RIFF", b"not a wav at all, just text"])
def test_broken_wav_counts_as_missing_and_is_re_recorded(tmp_path: Path, bad: bytes) -> None:
    lines = ["[warm] hi"]
    cached = make(tmp_path)
    path = cached.cache.path_for(cached.key_for(lines[0]))
    path.write_bytes(bad)
    assert missing(lines, cached) == lines
    assert record(lines, cached) == 1
    assert path.read_bytes() != bad  # the bad file was overwritten
    assert missing(lines, cached) == []


def test_describe_error_shows_our_own_messages() -> None:
    assert describe_error(ValueError("13 requests needed, cap is 12")) == (
        "ValueError: 13 requests needed, cap is 12"
    )
    assert describe_error(SpeechError("speech reply is not a WAV")) == (
        "SpeechError: speech reply is not a WAV"
    )
    assert "MissingKeyError: GROQ_API_KEY" in describe_error(MissingKeyError("GROQ_API_KEY"))
    assert describe_error(CacheMiss("no audio")) == "CacheMiss: no audio"


class SdkError(Exception):
    """Stands in for an SDK error that carries the key in str() and .request."""

    def __init__(self) -> None:
        super().__init__("Bearer sk-secret-test rejected")
        self.status_code = 429
        self.request = "headers: Authorization sk-secret-test"


def test_describe_error_hides_sdk_details() -> None:
    out = describe_error(SdkError())
    assert "429" in out
    assert "SdkError" in out
    assert "sk-secret-test" not in out


def test_describe_error_without_status() -> None:
    assert describe_error(RuntimeError("secret sk-x")) == "RuntimeError"
