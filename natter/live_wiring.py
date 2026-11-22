"""Builds a LiveCall with the real providers and the speech safety stack."""

from pathlib import Path

from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.live import SPEECH_CAP, LiveCall
from natter.providers.base import Extractor, Persona, Speech
from natter.providers.claude_extractor import ClaudeExtractor
from natter.providers.groq_persona import GroqPersona
from natter.providers.groq_speech import GroqSpeech
from natter.speech_budget import BudgetedSpeech
from natter.throttle import Throttle, ThrottledSpeech

ROOT = Path(__file__).parent.parent  # the project folder, not the current directory
LIVE_AUDIO = ROOT / "live_cache" / "audio"  # gitignored; WAVs from live calls are kept here


def build_live_call(
    persona: Persona,
    extractor: Extractor,
    speech: Speech,
    audio_dir: Path,
    speech_cap: int = SPEECH_CAP,
    throttle_gap_s: float = 7.0,
) -> LiveCall:
    """Wrap speech as cache -> budget -> throttle -> speech, and hand the budget to LiveCall.

    The budget is INSIDE the cache (a cache hit is free) and OUTSIDE the throttle
    (a refused line does not wait). LiveCall gets the same budget object to read its count.
    """
    budget = BudgetedSpeech(ThrottledSpeech(speech, Throttle(throttle_gap_s)), speech_cap)
    # evict_oldest: a long session deletes its oldest WAVs instead of filling the folder
    cache = AudioCache(audio_dir, "record", evict_oldest=True)
    stack = CachedSpeech(budget, cache, speech_key)
    return LiveCall(persona, extractor, stack, budget=budget)


def make_live_call(
    audio_dir: Path = LIVE_AUDIO, speech_cap: int = SPEECH_CAP, speech: bool = True
) -> LiveCall:
    """The real providers. Each reads its own key from the environment; a missing key
    raises MissingKeyError here, before any call is made.

    speech=False (--no-speech): no speech provider, no budget and no audio folder,
    so no speech request can ever be made.
    """
    if not speech:
        return LiveCall(GroqPersona(), ClaudeExtractor(), None)
    return build_live_call(GroqPersona(), ClaudeExtractor(), GroqSpeech(), audio_dir, speech_cap)
