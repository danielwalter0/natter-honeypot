"""A provider that can only be replayed. Lets cached answers play back with no keys."""

from natter.picker import Goal
from natter.schema import Dossier, Turn


class ReplayOnly:
    """Satisfies Persona, Extractor and Speech. Any real call is a bug, so it raises."""

    def __init__(self, name: str) -> None:
        self.name = name  # must match the name the cache was recorded under

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        raise RuntimeError("replay-only provider was called")

    def extract(self, transcript: list[Turn]) -> Dossier:
        raise RuntimeError("replay-only provider was called")

    def speak(self, text: str) -> bytes:
        raise RuntimeError("replay-only provider was called")
