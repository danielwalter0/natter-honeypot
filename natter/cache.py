"""Record/replay cache for provider calls."""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from natter.picker import Goal
from natter.providers.base import Extractor, Persona
from natter.schema import Dossier, Turn

MAX_REPLY_CHARS = 2000


class CacheMiss(Exception):
    """Replay mode found no stored result for this key."""


def checked_reply(value: object) -> str:
    """Accept only a non-empty piece of text of sensible length."""
    if not isinstance(value, str):
        raise ValueError("persona reply is not text")
    if not value.strip() or len(value) > MAX_REPLY_CHARS:
        raise ValueError("persona reply is empty or too long")
    return value


def cache_key(provider: str, method: str, inputs: dict[str, object]) -> str:
    """Return the sha256 hex digest of the canonical JSON of the call.

    Canonical JSON is the dict {"provider": provider, "method": method,
    "inputs": inputs} passed through:
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True, allow_nan=False).encode("utf-8")
    Dict key order must not change the key. Changing the provider, the method
    or any input value must change the key.
    """
    call = {"provider": provider, "method": method, "inputs": inputs}
    text = json.dumps(
        call, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    data = text.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Cache:
    """A folder of JSON files, one per key.

    Contract:
    - Keys match ^[0-9a-f]{64}$. File names come from the hash only, so text
      from the inputs never reaches a path.
    - A file holds JSON only: {"provider", "method", "result"}. Never the
      inputs, provider attributes or env values. Never pickle.
    """

    def __init__(self, folder: Path, mode: Literal["replay", "record"]) -> None:
        if mode not in ("replay", "record"):
            raise ValueError(f"unknown cache mode: {mode!r}")
        self.folder = folder
        self.mode = mode

    def path_for(self, key: str) -> Path:
        """Return folder / f"{key}.json". A key not matching the regex raises ValueError."""
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise ValueError(f"bad cache key: {key!r}")
        return self.folder.joinpath(f"{key}.json")

    def load(self, key: str) -> object:
        """Return the parsed "result" from the file. A missing file raises CacheMiss."""
        path = self.path_for(key)
        if not path.exists():
            raise CacheMiss(f"no cached answer for {key}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["result"]

    def store(self, key: str, provider: str, method: str, result: object) -> None:
        """Write {"provider", "method", "result"} as JSON to path_for(key)."""
        path = self.path_for(key)
        self.folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"provider": provider, "method": method, "result": result})
        path.write_text(text, encoding="utf-8")


class CachedPersona:
    """Wraps a Persona with the cache. Also satisfies Persona.

    inputs = {"transcript": [t.model_dump(mode="json") for t in transcript],
              "goal": the goal's string value, or None}
    - replay mode: a miss raises CacheMiss and the inner persona is never called.
    - record mode: a miss calls the inner persona, stores the string and returns
      it. A hit returns the stored string without calling the inner persona.
    - The key is cache_key(inner.name, "reply", inputs), and a store is
      cache.store(key, inner.name, "reply", result).
    """

    def __init__(self, inner: Persona, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.name = inner.name

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        inputs: dict[str, object] = {
            "transcript": [turn.model_dump(mode="json") for turn in transcript],
            "goal": None if goal is None else str(goal),
        }
        key = cache_key(self.name, "reply", inputs)

        try:
            return checked_reply(self.cache.load(key))
        except CacheMiss:
            if self.cache.mode != "record":
                raise

        result = checked_reply(self.inner.reply(transcript, goal))
        self.cache.store(key, self.name, "reply", result)
        return result


class CachedExtractor:
    """Wraps an Extractor with the cache. Also satisfies Extractor.

    inputs = {"transcript": [t.model_dump(mode="json") for t in transcript]}
    - replay mode: a miss raises CacheMiss and the inner extractor is never
      called. A hit is Dossier.model_validate(loaded), so a bad file fails.
    - record mode: a miss calls the inner extractor and stores
      dossier.model_dump(mode="json"). A hit returns the stored dossier
      without calling the inner extractor.
    - The key is cache_key(inner.name, "extract", inputs), and a store is
      cache.store(key, inner.name, "extract", result).
    """

    def __init__(self, inner: Extractor, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.name = inner.name

    def extract(self, transcript: list[Turn]) -> Dossier:
        inputs: dict[str, object] = {
            "transcript": [turn.model_dump(mode="json") for turn in transcript]
        }
        key = cache_key(self.name, "extract", inputs)

        try:
            return Dossier.model_validate(self.cache.load(key))
        except CacheMiss:
            if self.cache.mode != "record":
                raise

        dossier = self.inner.extract(transcript)
        self.cache.store(key, self.name, "extract", dossier.model_dump(mode="json"))
        return dossier
