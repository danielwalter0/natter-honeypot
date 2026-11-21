"""Wiring for the web page: a LiveCall built from replay-only parts."""

from pathlib import Path

from natter.__main__ import SCENARIO, load_lines, replay_providers
from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.live import LiveCall
from natter.providers import groq_speech
from natter.providers.replay_only import ReplayOnly


def make_replay_call(scenario: Path = SCENARIO) -> tuple[LiveCall, list[str]]:
    """A LiveCall that replays the saved scenario: no keys, no network, no writes."""
    persona, extractor = replay_providers(scenario / "cache")
    # ReplayOnly refuses to speak for real; a cache miss is an error, never a paid call
    speech = CachedSpeech(
        ReplayOnly(groq_speech.NAME), AudioCache(scenario / "audio", "replay"), speech_key
    )
    return LiveCall(persona, extractor, speech, budget=None), load_lines(scenario)
