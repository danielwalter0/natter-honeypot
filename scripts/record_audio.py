"""Record Natter's spoken lines for bank-fraud-01 as WAV files.

Run by the owner only. Needs GROQ_API_KEY set in the shell. Never prints the key.
Replays the text cassettes to find the persona lines, then voices the missing ones.
"""

import sys

from natter.__main__ import CACHE, MAX_TURNS, SCENARIO, load_lines, replay_providers
from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.audio_record import describe_error, missing, persona_lines, record
from natter.providers import groq_speech
from natter.providers.groq_speech import GroqSpeech
from natter.providers.replay_only import ReplayOnly
from natter.session import run_session
from natter.throttle import Throttle, ThrottledSpeech

AUDIO = SCENARIO / "audio"


def main() -> None:
    # Replay mode only reads the text cassettes. It never writes them.
    persona, extractor = replay_providers(CACHE)
    result = run_session(load_lines(SCENARIO), persona, extractor, MAX_TURNS)
    lines = persona_lines(result.transcript)
    cache = AudioCache(AUDIO, "record")
    # Same name and key builder as the real one, but it can never call out, so no key is needed
    preview = CachedSpeech(ReplayOnly(groq_speech.NAME), cache, speech_key)
    todo = missing(lines, preview)
    print(f"Lines: {len(lines)}, missing: {len(todo)}, characters: {sum(map(len, todo))}")
    if not todo:
        print("Nothing to record.")
        return
    # Built only now, so a run with nothing to do needs no key
    try:
        cached = CachedSpeech(ThrottledSpeech(GroqSpeech(), Throttle(7.0)), cache, speech_key)
        # record() re-checks on this object, so the cap covers the lines really called
        calls = record(lines, cached)
    except Exception as exc:
        # describe_error never prints SDK error text, which can carry the key
        print(f"stopped: {describe_error(exc)}")
        sys.exit(1)
    files = list(AUDIO.glob("*.wav"))
    print(f"Calls: {calls}")
    print(f"WAV files: {len(files)}, {sum(f.stat().st_size for f in files) // 1024} KB")


if __name__ == "__main__":
    main()
