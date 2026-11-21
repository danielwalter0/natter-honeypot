"""Logic for the audio recorder: which lines to voice, and a capped record run."""

from natter.audio_cache import CachedSpeech
from natter.cache import CacheMiss
from natter.providers.errors import MissingKeyError, SpeechError
from natter.schema import Turn
from natter.speech_text import DIRECTION, prepare_speech_text

AUDIO_CAP_REQUESTS = 12  # the most real calls one run may make


def persona_lines(transcript: list[Turn]) -> list[str]:
    """Prepared text for each persona turn, in order. Scammer turns are not voiced."""
    return [prepare_speech_text(t.text, DIRECTION) for t in transcript if t.speaker == "persona"]


def missing(lines: list[str], cached: CachedSpeech) -> list[str]:
    """Lines with no good stored WAV yet (a broken file counts as missing). Order kept."""
    return [line for line in dict.fromkeys(lines) if not cached.cache.has(cached.key_for(line))]


def record(lines: list[str], cached: CachedSpeech, max_requests: int = AUDIO_CAP_REQUESTS) -> int:
    """Speak every missing line once. Returns the number of real calls made.

    The pre-flight check runs on the same object that then speaks, so the cap
    always covers exactly the lines that will be called. Errors are not caught:
    the first one ends the run. Lines already stored stay stored, so a rerun resumes.
    """
    todo = missing(lines, cached)
    # Pre-flight check: refuse before any call, so a bug cannot send dozens of requests
    if len(todo) > max_requests:
        raise ValueError(f"{len(todo)} requests needed, cap is {max_requests}")
    for line in todo:
        cached.speak(line)
    return len(todo)


def describe_error(exc: BaseException) -> str:
    """A one-line description that is safe to print.

    Our own errors carry messages we wrote, which hold no key. Anything else is
    an SDK error whose text and .request can hold the key, so only its type
    and status are shown.
    """
    if isinstance(exc, (ValueError, SpeechError, MissingKeyError, CacheMiss)):
        return f"{type(exc).__name__}: {exc}"
    status = getattr(exc, "status_code", None)
    extra = f" status {status}" if status is not None else ""
    return f"{type(exc).__name__}{extra}"
