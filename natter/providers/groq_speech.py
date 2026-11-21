"""Real speech: Groq text-to-speech. No tools. Returns WAV bytes."""

import os
from collections.abc import Callable

import groq

from natter.audio_cache import is_wav
from natter.providers.errors import MissingKeyError, SpeechError

MODEL = "canopylabs/orpheus-v1-english"
VOICE = "diana"
MAX_INPUT_CHARS = 200  # Orpheus rejects longer input; a rejected call still uses quota
NAME = f"groq:{MODEL}:{VOICE}"  # replay needs the name without a key


class GroqSpeech:
    """Calls Groq once per line. Satisfies the Speech protocol."""

    def __init__(self, client_factory: Callable[..., groq.Groq] = groq.Groq) -> None:
        # The only place the key is read
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise MissingKeyError("GROQ_API_KEY is not set")
        # max_retries=0 on purpose: the SDK default of 2 would turn one 429 into
        # 3 requests against a 10 requests/minute, 100 requests/day free tier
        self.client = client_factory(api_key=key, timeout=30.0, max_retries=0)
        self.name = NAME

    def speak(self, text: str) -> bytes:
        # Checked here, before the network, because a rejected call still costs quota
        if not text.strip():
            raise SpeechError("speech text is empty")
        if len(text) > MAX_INPUT_CHARS:
            raise SpeechError("speech text is over 200 characters")
        # No sample_rate: the 24 kHz default works and a bad value wastes a request
        resp = self.client.audio.speech.create(
            model=MODEL, voice=VOICE, input=text, response_format="wav"
        )
        data = resp.read()
        if not is_wav(data):  # empty bytes fail here too
            raise SpeechError("speech reply is not a WAV")
        return data
