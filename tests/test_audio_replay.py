import pytest

from natter.__main__ import CACHE, MAX_TURNS, SCENARIO, load_lines, replay_providers
from natter.audio_cache import MAX_FOLDER_BYTES, MAX_WAV_BYTES, AudioCache, CachedSpeech, is_wav
from natter.audio_key import speech_key
from natter.audio_record import persona_lines
from natter.providers import groq_speech
from natter.providers.replay_only import ReplayOnly
from natter.session import run_session

AUDIO = SCENARIO / "audio"

EXPECTED_LINES = 10  # persona replies in the bank-fraud-01 text cassettes


def test_audio_folder_is_committed() -> None:
    # Fail, never skip: a fresh clone must replay with sound and no keys
    assert AUDIO.is_dir(), "audio missing: run scripts/record_audio.py"
    assert len(list(AUDIO.glob("*.wav"))) == EXPECTED_LINES


def test_replay_speaks_every_persona_line_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    persona, extractor = replay_providers(CACHE)
    result = run_session(load_lines(SCENARIO), persona, extractor, MAX_TURNS)
    speech = CachedSpeech(ReplayOnly(groq_speech.NAME), AudioCache(AUDIO, "replay"), speech_key)
    for line in persona_lines(result.transcript):
        assert is_wav(speech.speak(line))


def test_audio_folder_matches_the_persona_lines() -> None:
    persona, extractor = replay_providers(CACHE)
    result = run_session(load_lines(SCENARIO), persona, extractor, MAX_TURNS)
    cached = CachedSpeech(ReplayOnly(groq_speech.NAME), AudioCache(AUDIO, "replay"), speech_key)
    expected = {f"{cached.key_for(line)}.wav" for line in persona_lines(result.transcript)}
    assert len(expected) == EXPECTED_LINES
    files = list(AUDIO.iterdir())  # raises if the folder is missing, so the test fails
    assert {f.name for f in files} == expected  # no strays, nothing missing, no .tmp
    assert all(f.stat().st_size <= MAX_WAV_BYTES for f in files)
    assert sum(f.stat().st_size for f in files) <= MAX_FOLDER_BYTES
