"""Compare persona replies across Groq models. Owner-run spike, not product code.

Needs GROQ_API_KEY in the shell. Text calls to Groq only: no Claude, no speech.
For each model, plays the caller lines as --runs separate conversations (each built
from her own replies), then prints one block per caller line with the replies and
the seconds each call took. Output also goes to spike_out/.
On a 429 it waits for the retry-after header (at most 60 s) and retries that call
once. Any other error, or a second failure, stops the run with the model, the line
number, the error type and status, and the retry-after header. Nothing else from
the error is printed.
"""

import argparse
import time
from pathlib import Path
from typing import Any

import groq

from natter.providers import groq_persona
from natter.providers.groq_persona import DEFAULT_MODEL, GroqPersona
from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import Turn

CALLER_LINES = [
    "Hello, is this the account holder?",
    "Your bank account has been compromised, we need to act now.",
    "I need a callback number from you.",
    "You need to transfer the money to a safe account today.",
    "Hurry up, I'm very busy.",
    "Don't tell anyone about this call.",
    "What? Speak up, I can't hear you.",
    "Are you a robot?",
]
MAX_WAIT_S = 60.0  # longest wait on a 429, whatever retry-after says
NO_HEADER_WAIT_S = 10.0  # wait on a 429 that has no usable retry-after header
OUT_DIR = Path("spike_out")  # gitignored
COMPARE_FILE = OUT_DIR / "persona_compare.txt"  # always written


class CallFailed(Exception):
    """Where the run stopped. Holds only safe facts, never the error's message."""

    def __init__(self, model: str, line_no: int, err: Exception) -> None:
        status = getattr(err, "status_code", "none")
        retry_after = retry_after_header(err) or "none"
        super().__init__(
            f"model {model}, line {line_no}, {type(err).__name__}, status {status}, "
            f"retry-after {retry_after}"
        )


def no_retry_client(**kwargs: Any) -> groq.Groq:
    # GroqPersona asks the SDK for one retry; this script does its own single retry
    return groq.Groq(**{**kwargs, "max_retries": 0})


def retry_after_header(err: Exception) -> str | None:
    """The retry-after response header, if the error has a response that carries one."""
    response = getattr(err, "response", None)
    if response is None:
        return None
    value = response.headers.get("retry-after")
    return str(value)[:20] if value is not None else None  # short: a header only


def wait_seconds(err: Exception) -> float:
    """How long to wait before the one retry: retry-after in seconds, capped at 60."""
    try:
        return min(float(retry_after_header(err) or NO_HEADER_WAIT_S), MAX_WAIT_S)
    except ValueError:  # not a number (an HTTP date, say): use the default wait
        return NO_HEADER_WAIT_S


def timed_reply(persona: GroqPersona, transcript: list[Turn]) -> tuple[str, float]:
    """(reply, seconds) for one call. On a 429, wait and retry once; the retry is timed."""
    try:
        start = time.perf_counter()
        return persona.reply(transcript, None), time.perf_counter() - start
    except groq.RateLimitError as err:
        wait = wait_seconds(err)
        print(f"429 on {persona.model}: waiting {wait:.0f} s, then one retry", flush=True)
        time.sleep(wait)
        start = time.perf_counter()
        return persona.reply(transcript, None), time.perf_counter() - start


def play(persona: GroqPersona, pause_s: float) -> list[tuple[str, float]]:
    """One conversation: (reply, seconds) for each caller line, in order."""
    transcript: list[Turn] = []
    results = []
    for i, line in enumerate(CALLER_LINES):
        transcript.append(Turn(index=len(transcript), speaker="scammer", text=line))
        try:
            reply, seconds = timed_reply(persona, transcript)  # no goal: only the prompt
        except Exception as err:
            raise CallFailed(persona.model, i + 1, err) from None
        results.append((reply, seconds))
        transcript.append(Turn(index=len(transcript), speaker="persona", text=reply))
        time.sleep(pause_s)  # not timed; keeps the run under the per-minute limit
    return results


def report(model: str, runs: list[list[tuple[str, float]]]) -> list[str]:
    """Printable lines: one block per caller line, then the model's average."""
    out = [f"=== {model} ==="]
    for i, line in enumerate(CALLER_LINES):
        out.append(f"[{i + 1}] Caller: {line}")
        for n, run in enumerate(runs, start=1):
            reply, seconds = run[i]
            stall = "  (SAFE STALL)" if reply == SAFE_STALL else ""
            out.append(f"    run {n} ({seconds:.2f} s, {len(reply)} chars): {reply}{stall}")
    times = [seconds for run in runs for _, seconds in run]
    out.append(f"average: {sum(times) / len(times):.2f} s per call over {len(times)} calls")
    return out + [""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=[DEFAULT_MODEL, "openai/gpt-oss-20b"])
    parser.add_argument("--runs", type=int, default=2, help="conversations per model")
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between calls")
    parser.add_argument("--out", default=str(COMPARE_FILE), help="extra copy of the output")
    # Spike only: swap in a saved prompt (e.g. spike_out/prompt_before.txt) for a
    # before/after comparison. build_messages reads SYSTEM_PROMPT at call time.
    parser.add_argument("--prompt-file", help="use this file's text as the system prompt")
    args = parser.parse_args()
    if args.runs < 1 or args.pause < 0:
        parser.error("--runs must be 1 or more and --pause 0 or more")

    if args.prompt_file:
        groq_persona.SYSTEM_PROMPT = Path(args.prompt_file).read_text(encoding="utf-8")
    lines: list[str] = []
    try:
        # Check every model id against Groq's live list before spending any calls
        first = GroqPersona(model=args.models[0], client_factory=no_retry_client)
        try:
            available = {m.id for m in first.client.models.list().data}
        except Exception as err:
            raise CallFailed(args.models[0], 0, err) from None  # line 0: the model list
        for model in args.models:
            if model not in available:
                lines += [f"=== {model} ===", "not available on Groq, skipped", ""]
                continue
            persona = GroqPersona(model=model, client_factory=no_retry_client)
            lines += report(model, [play(persona, args.pause) for _ in range(args.runs)])
    except CallFailed as stop:
        lines.append(f"Stopped: {stop}")
    except Exception as err:  # e.g. MissingKeyError before any call
        lines.append(f"Stopped: {type(err).__name__}")
    text = "\n".join(lines) + "\n"
    print(text, end="")
    OUT_DIR.mkdir(exist_ok=True)
    COMPARE_FILE.write_text(text, encoding="utf-8")
    Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
