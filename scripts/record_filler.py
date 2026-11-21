"""Record the eight latency filler lines as WAV files in assets/filler/.

Run by the owner only. Needs GROQ_API_KEY set in the shell. Never prints the key.
Same speech stack as record_audio.py: throttled, capped, and stored through the cache,
so a rerun only voices the lines that are still missing.
"""

import sys

from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.audio_record import missing, record
from natter.filler import FILLER_FOLDER, filler_texts
from natter.providers import groq_speech
from natter.providers.groq_speech import GroqSpeech
from natter.providers.replay_only import ReplayOnly
from natter.speech_budget import BudgetedSpeech
from natter.throttle import Throttle, ThrottledSpeech

FILLER_CAP_REQUESTS = 10  # the most real calls one run may make (there are eight lines)


def main() -> None:
    texts = filler_texts()
    cache = AudioCache(FILLER_FOLDER, "record")
    # Same name and key builder as the real one, but it can never call out, so no key is needed
    preview = CachedSpeech(ReplayOnly(groq_speech.NAME), cache, speech_key)
    todo = missing(texts, preview)
    print(f"Filler lines: {len(texts)}, requests to make: {len(todo)}")
    if not todo:
        print("Nothing to record.")
        return
    # Built only now, so a run with nothing to do needs no key. GroqSpeech never retries.
    try:
        speech = BudgetedSpeech(ThrottledSpeech(GroqSpeech(), Throttle(7.0)), FILLER_CAP_REQUESTS)
        cached = CachedSpeech(speech, cache, speech_key)
        # record() re-checks on this object, so the cap covers the lines really called
        calls = record(texts, cached, FILLER_CAP_REQUESTS)
    except Exception as exc:
        # Type and status only: an error's text could carry request details
        status = getattr(exc, "status_code", None)
        extra = f" status {status}" if status is not None else ""
        print(f"stopped: {type(exc).__name__}{extra}")
        sys.exit(1)
    files = list(FILLER_FOLDER.glob("*.wav"))
    print(f"Calls: {calls}")
    print(f"WAV files: {len(files)}, {sum(f.stat().st_size for f in files) // 1024} KB")


if __name__ == "__main__":
    main()
