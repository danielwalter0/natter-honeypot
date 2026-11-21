"""Provider interfaces. Real and fake providers both match these shapes."""

from typing import Protocol

from natter.picker import Goal
from natter.schema import Dossier, Turn


class Persona(Protocol):
    """The granny voice. It has no tools and only a fake identity.

    Transcript text is untrusted data (the scammer wrote it). Implementations
    must delimit it as data and never treat it as instructions.
    """

    name: str  # e.g. "fake-persona"; goes into the cache key

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        """Return the persona's next line, steering toward goal if there is one."""
        ...


class Speech(Protocol):
    """Turns persona text into spoken audio. It has no tools.

    The text is persona model output that has already been prepared (brackets
    stripped, direction added, at most 200 characters). The result is WAV bytes.
    """

    name: str  # goes into the cache key

    def speak(self, text: str) -> bytes:
        """Return WAV bytes for the text."""
        ...


class Extractor(Protocol):
    """Reads the transcript and proposes facts for the dossier."""

    name: str  # goes into the cache key

    def extract(self, transcript: list[Turn]) -> Dossier:
        """Return a PROPOSED dossier.

        It is untrusted until check_dossier (natter/check.py) validates it.
        Transcript text is untrusted data and must never act as an instruction.
        """
        ...
