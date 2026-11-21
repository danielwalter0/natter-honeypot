"""Tests for the latency filler lines and loading their recorded clips. No keys."""

import base64
from pathlib import Path

import pytest

from natter.audio_cache import is_wav
from natter.audio_key import speech_key
from natter.filler import FILLER_FOLDER, FILLER_LINES, filler_texts, load_filler_urls
from natter.providers import groq_speech
from natter.providers.fakes import FakeSpeech
from natter.speech_text import DIRECTION, prepare_speech_text

WAV = FakeSpeech().speak("x")  # a small valid WAV
NAME = groq_speech.NAME


def store_all(folder: Path) -> None:
    """Write a fake WAV under the real key of every filler line."""
    folder.mkdir(parents=True, exist_ok=True)
    for text in filler_texts():
        (folder / f"{speech_key(NAME, text)}.wav").write_bytes(WAV)


def test_eight_short_plain_filler_lines() -> None:
    assert len(FILLER_LINES) == 8
    assert len(set(FILLER_LINES)) == 8  # no repeats
    for line in FILLER_LINES:
        assert len(line) < 40
        assert not any(ch.isdigit() for ch in line)
        assert not any(ch in "-–—" for ch in line)  # hyphen, en, em dash


def test_filler_texts_are_prepared_like_persona_lines() -> None:
    assert filler_texts() == [prepare_speech_text(line, DIRECTION) for line in FILLER_LINES]


def test_missing_or_empty_folder_gives_no_filler(tmp_path: Path) -> None:
    assert load_filler_urls(tmp_path / "missing", NAME) == []
    assert load_filler_urls(tmp_path, NAME) == []


def test_recorded_clips_load_as_wav_data_urls(tmp_path: Path) -> None:
    store_all(tmp_path)
    urls = load_filler_urls(tmp_path, NAME)
    assert len(urls) == 8
    expected = "data:audio/wav;base64," + base64.b64encode(WAV).decode("ascii")
    assert all(url == expected for url in urls)


def test_bad_and_unknown_files_are_skipped(tmp_path: Path) -> None:
    store_all(tmp_path)
    first = speech_key(NAME, filler_texts()[0])
    (tmp_path / f"{first}.wav").write_bytes(b"not a wav")  # a broken clip
    (tmp_path / f"{'a' * 64}.wav").write_bytes(WAV)  # a WAV that is not a filler line
    assert len(load_filler_urls(tmp_path, NAME)) == 7


@pytest.mark.skipif(not FILLER_FOLDER.exists(), reason="fillers not recorded yet")
def test_committed_folder_holds_exactly_the_eight_filler_wavs() -> None:
    files = sorted(FILLER_FOLDER.glob("*.wav"))
    expected = sorted(f"{speech_key(NAME, text)}.wav" for text in filler_texts())
    assert [f.name for f in files] == expected
    assert all(is_wav(f.read_bytes()) for f in files)
    assert len(load_filler_urls(FILLER_FOLDER, NAME)) == 8
