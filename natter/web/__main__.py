"""Launch the page: `python -m natter.web --replay` (no keys) or `--live` (keys needed).

The server binds to 127.0.0.1 only, so nothing outside this computer can reach it.
"""

import argparse
import sys
from collections.abc import Callable
from typing import Any

import uvicorn
from fastapi import FastAPI

from natter.filler import FILLER_FOLDER, load_filler_urls
from natter.live import SPEECH_CAP
from natter.live_wiring import make_live_call
from natter.providers import groq_speech
from natter.providers.errors import MissingKeyError
from natter.web.server import create_app
from natter.web_wiring import make_replay_call

HOST = "127.0.0.1"  # localhost only; never 0.0.0.0
PORT = 8000  # must match the Host and Origin allow-lists in server.py

SPEND_WARNING = (
    "WARNING: No daily spend cap is built yet. Each call is capped (40 turns, "
    "20 extractions, 15 speech requests, 10 minutes), but restarting the server "
    "or pressing Reset starts a fresh call with fresh caps."
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """--replay or --live, never both. No flag means replay."""
    parser = argparse.ArgumentParser(prog="python -m natter.web")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--replay", action="store_true", help="recorded call, no keys (default)")
    group.add_argument("--live", action="store_true", help="type scammer lines; needs API keys")
    parser.add_argument(
        "--no-speech", action="store_true", help="live only: text replies, no speech requests"
    )
    args = parser.parse_args(argv)
    if args.no_speech and not args.live:
        parser.error("--no-speech needs --live")  # exits with code 2
    return args


def build_app(live: bool, speech: bool = True) -> FastAPI:
    """The app for one mode. A missing key in live mode raises MissingKeyError."""
    if live and not speech:
        # Rehearsals and evaluation runs: no speech budget, no cap and no filler clips.
        # A speech_cap of None tells the page that speech is off.
        print("Speech is off: replies are text only.")
        return create_app("live", lambda: make_live_call(speech=False), None, None, PORT, [])
    if live:
        print(SPEND_WARNING)
        # The filler clips are read once, here. FILLER_FOLDER is looked up at call
        # time too, so tests can point it at a temporary folder
        filler = load_filler_urls(FILLER_FOLDER, groq_speech.NAME)
        # make_live_call is looked up at call time, so tests can swap it for a fake
        return create_app("live", make_live_call, None, SPEECH_CAP, PORT, filler)
    _, lines = make_replay_call()
    # Reset builds a fresh replay call; the lines never change, so they are passed once
    return create_app("replay", lambda: make_replay_call()[0], lines, None, PORT)


def main(argv: list[str] | None = None, run: Callable[..., Any] = uvicorn.run) -> None:
    """argv=None reads sys.argv. Tests pass a fake `run` so no server starts."""
    # Same as natter/__main__.py: a cp1252 console must not crash on a model's characters
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        app = build_app(args.live, speech=not args.no_speech)
    except MissingKeyError as exc:  # the text names the variable, never a key
        print(exc)
        raise SystemExit(1) from None
    print(f"Open http://{HOST}:{PORT} in a browser. Ctrl+C stops the server.")
    # server_header=False: do not advertise the server software in responses
    run(app, host=HOST, port=PORT, server_header=False)


if __name__ == "__main__":
    main()
