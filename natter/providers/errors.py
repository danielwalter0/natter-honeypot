"""Errors shared by the real providers."""


class MissingKeyError(Exception):
    """An API key env var is not set. The message names the variable, never a value."""


class ExtractionError(Exception):
    """The extractor reply was unusable. The caller gets no partial dossier."""


class PersonaError(Exception):
    """The persona reply was unusable (no choice, no message, or it did not finish cleanly)."""


class SpeechError(Exception):
    """The speech reply was unusable (not a WAV)."""
