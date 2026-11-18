"""Fake providers for tests and replay. No network, no randomness, no env reads."""

from natter.picker import Goal
from natter.schema import Dossier, Turn

DEFAULT_LINES = [
    "Oh hello dear, hold on, let me find my glasses.",
    "Sorry, could you say that again? The kettle is whistling.",
    "My cat is sitting on the phone book, give me a moment.",
]


class FakePersona:
    """Returns its lines in order and cycles back to the start."""

    name = "fake-persona"

    def __init__(self, lines: list[str] | None = None) -> None:
        self.lines = list(DEFAULT_LINES if lines is None else lines)
        if not self.lines:
            raise ValueError("lines must not be empty")
        self.position = 0  # index of the next line to return

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        # Inputs are ignored on purpose, which keeps the fake deterministic
        line = self.lines[self.position % len(self.lines)]
        self.position += 1
        return line


class FakeExtractor:
    """Always proposes the dossier it was given."""

    name = "fake-extractor"

    def __init__(self, dossier: Dossier) -> None:
        self.dossier = dossier

    def extract(self, transcript: list[Turn]) -> Dossier:
        # Deep copy so callers cannot change the preset
        return self.dossier.model_copy(deep=True)
