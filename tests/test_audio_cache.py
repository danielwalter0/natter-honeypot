import hashlib
from pathlib import Path

import pytest

from natter import audio_cache
from natter.audio_cache import AudioCache, CachedSpeech, is_wav
from natter.cache import CacheMiss
from natter.providers.fakes import FakeSpeech
from natter.providers.replay_only import ReplayOnly

WAV = FakeSpeech().speak("x")  # a small valid WAV


def key_fn(provider: str, text: str) -> str:
    """Test-only stand-in for the real key builder."""
    return hashlib.sha256(f"{provider}|{text}".encode()).hexdigest()


KEY = key_fn("fake-speech", "hi")


def test_is_wav() -> None:
    assert is_wav(WAV)
    assert not is_wav(b"RIFF")
    assert not is_wav(b"x" * 100)
    assert not is_wav(b"")


def test_unknown_mode() -> None:
    with pytest.raises(ValueError):
        AudioCache(Path("."), "other")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["../x", KEY.upper(), "abc", KEY + "0", ""])
def test_bad_key(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        AudioCache(tmp_path, "record").path_for(bad)


def test_hit(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path, "replay")
    (tmp_path / f"{KEY}.wav").write_bytes(WAV)
    inner = ReplayOnly("fake-speech")
    assert CachedSpeech(inner, cache, key_fn).speak("hi") == WAV


def test_replay_miss_never_calls_inner(tmp_path: Path) -> None:
    inner = FakeSpeech()
    speech = CachedSpeech(inner, AudioCache(tmp_path, "replay"), key_fn)
    with pytest.raises(CacheMiss):
        speech.speak("hi")
    assert inner.texts == []


def test_record_miss_calls_inner_once_and_stores(tmp_path: Path) -> None:
    inner = FakeSpeech()
    speech = CachedSpeech(inner, AudioCache(tmp_path, "record"), key_fn)
    assert speech.speak("hi") == WAV
    assert inner.texts == ["hi"]
    assert (tmp_path / f"{KEY}.wav").read_bytes() == WAV
    assert list(tmp_path.glob("*.tmp")) == []


def test_record_hit_does_not_call_inner(tmp_path: Path) -> None:
    (tmp_path / f"{KEY}.wav").write_bytes(WAV)
    inner = FakeSpeech()
    speech = CachedSpeech(inner, AudioCache(tmp_path, "record"), key_fn)
    assert speech.speak("hi") == WAV
    assert inner.texts == []


def test_store_rejects_non_wav(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path, "record")
    with pytest.raises(ValueError):
        cache.store(KEY, b"not a wav at all")
    assert list(tmp_path.iterdir()) == []


def test_load_rejects_non_wav(tmp_path: Path) -> None:
    (tmp_path / f"{KEY}.wav").write_bytes(b"not a wav at all")
    with pytest.raises(ValueError):
        AudioCache(tmp_path, "replay").load(KEY)


def test_oversize_rejected_on_store_and_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio_cache, "MAX_WAV_BYTES", len(WAV) - 1)
    with pytest.raises(ValueError):
        AudioCache(tmp_path, "record").store(KEY, WAV)
    assert list(tmp_path.iterdir()) == []
    (tmp_path / f"{KEY}.wav").write_bytes(WAV)
    with pytest.raises(ValueError):
        AudioCache(tmp_path, "replay").load(KEY)


def test_folder_cap_rejects_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_cache, "MAX_FOLDER_BYTES", len(WAV) * 2)
    cache = AudioCache(tmp_path, "record")
    cache.store(key_fn("a", "1"), WAV)
    cache.store(key_fn("a", "2"), WAV)
    with pytest.raises(ValueError):
        cache.store(key_fn("a", "3"), WAV)
    # Replacing an existing file is allowed: its old size is not counted
    cache.store(key_fn("a", "1"), WAV)
    assert list(tmp_path.glob("*.tmp")) == []


def test_has_only_for_a_loadable_wav(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path, "record")
    assert not cache.has(KEY)  # no file
    cache.path_for(KEY).write_bytes(b"RIFF")
    assert not cache.has(KEY)  # truncated
    cache.path_for(KEY).write_bytes(b"x" * 100)
    assert not cache.has(KEY)  # not a WAV
    cache.path_for(KEY).write_bytes(WAV + b"\0" * audio_cache.MAX_WAV_BYTES)
    assert not cache.has(KEY)  # too big
    cache.store(KEY, WAV)
    assert cache.has(KEY)


def test_has_still_rejects_a_bad_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AudioCache(tmp_path, "record").has("../x")
