"""Terminal loop for `python -m natter.live`: type scammer lines, read Natter's replies.

Audio is not saved or played anywhere here; only its size is printed. (The speech
cache keeps its own copy of each WAV under live_cache/.)
"""

import sys

from natter.live_wiring import make_live_call
from natter.providers.errors import MissingKeyError


def main(argv: list[str] | None = None) -> None:
    """argv is unused; it is here to match the other entry points."""
    # Same as natter/__main__.py: a cp1252 console must not crash on a model's characters
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    try:
        call = make_live_call()
    except MissingKeyError as exc:  # the text names the variable, never a key
        print(exc)
        raise SystemExit(1) from None
    while True:
        try:
            line = input("scammer> ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == "quit":
            break
        reply = call.say(line)
        print(f"natter: {reply.text or '(no reply)'}")
        print(f"goal: {reply.goal.value if reply.goal else 'none'}")
        print(f"audio: {len(reply.audio)} bytes" if reply.audio else "audio: none")
        for note in reply.notes:
            print(f"note: {note}")
        print(f"speech requests used: {reply.speech_requests_used}")
        print(reply.dossier.model_dump_json(exclude_none=True))
        if reply.ended:
            break
