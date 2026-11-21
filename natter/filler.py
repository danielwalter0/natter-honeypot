"""Latency filler: short, generic lines Natter says while the real reply is being made.

The clips are recorded once by scripts/record_filler.py into assets/filler/ and the
live page plays them. They are never part of the transcript or the dossier.
"""

from pathlib import Path

from natter.audio_cache import AudioCache
from natter.audio_key import speech_key
from natter.speech_text import DIRECTION, prepare_speech_text
from natter.web_view import audio_url

# Committed folder, next to natter/ (not under scenarios/, which is evaluation data)
FILLER_FOLDER = Path(__file__).parent.parent / "assets" / "filler"

# Under 40 characters each, British, no digits, no dashes (a test checks)
FILLER_LINES = (
    "Oh, just a moment, dear.",
    "Hang on a second, love.",
    "Oh, hold on, let me think.",
    "Sorry dear, one moment.",
    "Oh, bear with me a moment.",
    "Just a second, my dear.",
    "Ooh, hang on there a moment.",
    "Oh, give me a moment, love.",
)


def filler_texts() -> list[str]:
    """The exact text sent to the voice for each line, prepared like persona lines."""
    return [prepare_speech_text(line, DIRECTION) for line in FILLER_LINES]


def load_filler_urls(folder: Path, provider_name: str) -> list[str]:
    """A WAV data URL for each filler line that has a good clip in the folder.

    Only the files named by our own keys are read, so a stray file is never served.
    A missing, too big or broken file is skipped. A missing folder gives [].
    """
    cache = AudioCache(folder, "replay")
    urls: list[str] = []
    for text in filler_texts():
        key = speech_key(provider_name, text)
        if cache.has(key):  # same checks as load(): exists, size cap, WAV marks
            url = audio_url(cache.load(key))
            if url is not None:  # audio_url only gives None for no audio
                urls.append(url)
    return urls
