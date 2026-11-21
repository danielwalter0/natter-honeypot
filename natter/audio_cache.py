"""Record/replay cache for spoken audio: a folder of WAV files, one per key."""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from natter.cache import CacheMiss
from natter.providers.base import Speech

MAX_WAV_BYTES = 1_000_000  # per file
MAX_FOLDER_BYTES = 8_000_000  # per scenario audio folder


def is_wav(data: bytes) -> bool:
    """Check only the RIFF/WAVE marks. Groq streams a placeholder length, so lengths are ignored."""
    return (
        isinstance(data, bytes) and len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    )


class AudioCache:
    """A folder of WAV files named by key. File names come from the hash only."""

    def __init__(self, folder: Path, mode: Literal["replay", "record"]) -> None:
        if mode not in ("replay", "record"):
            raise ValueError(f"unknown cache mode: {mode!r}")
        self.folder = folder
        self.mode = mode

    def path_for(self, key: str) -> Path:
        """Return folder / f"{key}.wav". A key that is not 64 lowercase hex chars raises."""
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise ValueError(f"bad cache key: {key!r}")
        return self.folder / f"{key}.wav"

    def load(self, key: str) -> bytes:
        """Return the stored WAV. Missing is CacheMiss; too big or not a WAV is ValueError."""
        path = self.path_for(key)
        if not path.exists():
            raise CacheMiss(f"no cached audio for {key}")
        # Check the size before reading so a huge file is never loaded
        if path.stat().st_size > MAX_WAV_BYTES:
            raise ValueError("cached audio is too big")
        data = path.read_bytes()
        if not is_wav(data):
            raise ValueError("cached audio is not a WAV")
        return data

    def has(self, key: str) -> bool:
        """True only when load(key) would succeed. A bad file is False; a bad key raises."""
        path = self.path_for(key)
        # Same checks as load(), in the same order, but answering instead of raising
        if not path.exists() or path.stat().st_size > MAX_WAV_BYTES:
            return False
        return is_wav(path.read_bytes())

    def store(self, key: str, data: bytes) -> None:
        """Validate, then write atomically. Nothing is written if a check fails."""
        path = self.path_for(key)
        if not is_wav(data):
            raise ValueError("audio is not a WAV")
        if len(data) > MAX_WAV_BYTES:
            raise ValueError("audio is too big")
        # Existing .wav files count, except the one this key would replace
        used = sum(f.stat().st_size for f in self.folder.glob("*.wav") if f != path)
        if used + len(data) > MAX_FOLDER_BYTES:
            raise ValueError("audio folder is full")
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / f"{key}.wav.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, path)  # a crash never leaves a half WAV under the real name


class CachedSpeech:
    """Wraps a Speech provider with the audio cache. Also satisfies Speech."""

    def __init__(self, inner: Speech, cache: AudioCache, key_fn: Callable[[str, str], str]) -> None:
        self.inner = inner
        self.cache = cache
        self.key_fn = key_fn  # key_fn(provider_name, text) -> 64-hex key
        self.name = inner.name

    def key_for(self, text: str) -> str:
        """The one place a cache key is built. Recorder and speak() both use it."""
        return self.key_fn(self.name, text)

    def speak(self, text: str) -> bytes:
        key = self.key_for(text)
        try:
            return self.cache.load(key)
        except (CacheMiss, ValueError):
            # Replay never calls the real provider, and a bad stored file is an error there.
            # Record mode treats a bad file like a miss: store() overwrites it.
            if self.cache.mode != "record":
                raise
        data = self.inner.speak(text)
        self.cache.store(key, data)  # store validates the bytes
        return data
