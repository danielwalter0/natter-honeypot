"""Try the persona prompt on six caller lines and print each reply. Owner-run only.

Needs GROQ_API_KEY in the shell. Text calls to Groq only: no Claude, no speech.
Writes nothing to disk. Stops at the first error and prints only its type and status.
"""

import argparse
import os
from typing import Any

import groq

from natter.picker import Goal
from natter.providers.groq_persona import DEFAULT_MODEL, GroqPersona
from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import Turn

CALLER_LINES = [
    "Good afternoon, I am calling from Kestrel Bank security. Is this Mrs Hargreaves?",
    "There has been a suspicious payment from your account and we must act now.",
    "Can you confirm the best phone number to reach you on?",
    "You need to move your savings to a protected account and I will guide you through it.",
    "Please read me the six digit code we just texted you.",
    "Now I need your card number and your PIN to verify that it is you.",
]


def no_retry_client(**kwargs: Any) -> groq.Groq:
    # GroqPersona asks the SDK for one retry; this script must stop at the first error
    return groq.Groq(**{**kwargs, "max_retries": 0})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Groq model for the persona")
    args = parser.parse_args()
    os.environ.pop("NATTER_RAW_LOG", None)  # the raw-reply debug log would write a file

    transcript: list[Turn] = []
    try:
        persona = GroqPersona(model=args.model, client_factory=no_retry_client)
        for i, line in enumerate(CALLER_LINES):
            transcript.append(Turn(index=len(transcript), speaker="scammer", text=line))
            goal = Goal.CALLBACK_NUMBER if i % 2 == 0 else None  # alternate goal and none
            reply = persona.reply(transcript, goal)
            transcript.append(Turn(index=len(transcript), speaker="persona", text=reply))
            print(f"\nCaller: {line}")
            print(f"Goal:   {goal}")
            print(f"Reply:  {reply}")
            print(f"Length: {len(reply)}  Safe stall: {reply == SAFE_STALL}")
    except Exception as err:
        # Type and status only: an error message could echo request details
        status = getattr(err, "status_code", "none")
        raise SystemExit(f"Stopped: {type(err).__name__}, status {status}") from None


if __name__ == "__main__":
    main()
