"""LiveCall: one scammer line in, one persona reply (text and audio) out.

Same turn logic as run_session (via the step functions in session.py), but a
provider failure degrades the reply instead of ending the call. say() never raises.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from natter.cache import CacheMiss, checked_reply
from natter.check import Rejection
from natter.picker import Goal
from natter.providers.base import Extractor, Persona, Speech
from natter.providers.errors import ExtractionError, MissingKeyError, PersonaError, SpeechError
from natter.providers.reply_tidy import SAFE_STALL, tidy_reply
from natter.schema import Dossier
from natter.session import (
    SessionState,
    add_persona_reply,
    add_scammer_line,
    apply_extraction,
    choose_goal,
    snapshot,
)
from natter.speech_budget import BudgetedSpeech, SpeechBudgetUsed
from natter.speech_text import DIRECTION, prepare_speech_text

MAX_TURNS = 40  # scammer and persona turns together
MAX_EXTRACTIONS = 20  # paid Claude calls per call
MAX_SECONDS = 600  # longest call
MAX_LINE_CHARS = 2000  # same as the Turn text limit
SPEECH_CAP = 15  # real speech requests per call; used by the later wiring (make_live_call)


@dataclass(frozen=True)
class LiveReply:
    """What say() hands back."""

    text: str | None  # None when no reply was made
    audio: bytes | None  # None when speech was skipped or failed
    dossier: Dossier  # latest checked dossier
    rejections: list[Rejection]  # drops from THIS turn only
    goal: Goal | None  # goal given to this reply
    ended: bool  # True once the call is over
    notes: list[str]  # short, safe reasons for anything that degraded
    speech_requests_used: int  # real speech requests so far


def _check_cap(name: str, value: object) -> None:
    """A cap must be a whole number, zero or more (a bool does not count)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a whole number, zero or more")


def safe_error(exc: BaseException) -> str:
    """A one-line description that is safe to show. Foreign errors show their type only."""
    # Our own errors carry messages we wrote. Anything else (SDK, pydantic, ValueError
    # that may quote a hostile line) can hold a key or scammer text, so no message.
    if isinstance(exc, (ExtractionError, PersonaError, SpeechError, MissingKeyError, CacheMiss)):
        return f"{type(exc).__name__}: {exc}"
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}" + (f" status {status}" if status is not None else "")


class LiveCall:
    """One live call. Holds one SessionState; say() is safe to call from two threads."""

    def __init__(
        self,
        persona: Persona,
        extractor: Extractor,
        speech: Speech,
        *,
        budget: BudgetedSpeech | None = None,  # the BudgetedSpeech inside `speech`, for counting
        max_turns: int = MAX_TURNS,
        max_extractions: int = MAX_EXTRACTIONS,
        max_seconds: float = MAX_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        _check_cap("max_turns", max_turns)
        _check_cap("max_extractions", max_extractions)
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)):
            raise ValueError("max_seconds must be a positive number")
        if not max_seconds > 0:  # also catches NaN
            raise ValueError("max_seconds must be a positive number")
        self.persona = persona
        self.extractor = extractor
        self.speech = speech
        self.budget = budget
        self.max_turns = max_turns
        self.max_extractions = max_extractions
        self.max_seconds = max_seconds
        self.clock = clock
        self.state = SessionState()
        self.extractions_used = 0
        self.ended = False
        self.started = clock()
        self._lock = threading.Lock()  # one say() at a time

    def _reply(
        self,
        text: str | None,
        goal: Goal | None,
        notes: list[str],
        *,
        audio: bytes | None = None,
        rejections: list[Rejection] | None = None,
    ) -> LiveReply:
        """Build a LiveReply from the current state."""
        used = self.budget.used if self.budget is not None else 0
        return LiveReply(
            text=text,
            audio=audio,
            dossier=self.state.dossier.model_copy(deep=True),  # a copy, so callers cannot edit ours
            rejections=rejections or [],
            goal=goal,
            ended=self.ended,
            notes=notes,
            speech_requests_used=used,
        )

    def _run_extraction(self) -> tuple[list[Rejection], list[str]]:
        """Run one extraction. Returns (this turn's drops, notes).

        Over the cap: no call. The count goes up BEFORE the call (a failed call still
        costs). On any failure the last checked dossier is kept and a safe note returned.
        """
        if self.extractions_used >= self.max_extractions:
            return ([], ["extraction cap reached"])
        self.extractions_used += 1
        try:
            proposed = self.extractor.extract(snapshot(self.state.transcript))
            dropped = apply_extraction(self.state, proposed)
            return (dropped, [])
        except Exception as exc:
            return ([], ["extraction failed: " + safe_error(exc)])

    def say(self, line: str) -> LiveReply:
        """Take one scammer line and return the persona's reply. Never raises."""
        with self._lock:
            return self._say(line)

    def _say(self, line: str) -> LiveReply:
        # 1. Caps: once over, the call is over, and no provider is touched
        if self.ended:
            return self._reply(None, None, ["call ended"])
        if len(self.state.transcript) >= self.max_turns:
            self.ended = True
            return self._reply(None, None, ["call ended: turn cap"])
        if self.clock() - self.started >= self.max_seconds:
            self.ended = True
            return self._reply(None, None, ["call ended: time cap"])
        # 2. Bad line: no turn is added and the call goes on
        if not isinstance(line, str) or not line.strip():
            return self._reply(None, None, ["line rejected: empty or not text"])
        if len(line) > MAX_LINE_CHARS:
            return self._reply(None, None, ["line rejected: too long"])
        try:
            line.encode("utf-8")  # a lone surrogate cannot be encoded
        except UnicodeEncodeError:
            return self._reply(None, None, ["line rejected: not valid text"])
        # 3-4. The scammer's turn, then the (possibly failing) extraction
        add_scammer_line(self.state, line.strip())
        rejections, notes = self._run_extraction()
        # 5. That turn may have used the last of the turn budget: no reply then
        if len(self.state.transcript) >= self.max_turns:
            self.ended = True
            return self._reply(None, None, notes, rejections=rejections)
        # 6. Persona. checked_reply rejects non-text and over-long output; tidy_reply
        # is defence in depth, so any persona (not only GroqPersona) is tidied.
        goal = choose_goal(self.state)
        try:
            raw = self.persona.reply(snapshot(self.state.transcript), goal)
            text = tidy_reply(checked_reply(raw), self.state.transcript)
            text.encode("utf-8")  # a lone surrogate raises here, so the stall is used
            # Proves there is something speakable; raises ValueError if not. Kept for step 7.
            spoken = prepare_speech_text(text, DIRECTION)
        except Exception as exc:
            text = SAFE_STALL
            spoken = prepare_speech_text(text, DIRECTION)
            goal = None  # she did not really ask, so previous_goal resets
            notes.append("persona failed: " + safe_error(exc))
        add_persona_reply(self.state, goal, text)
        if len(self.state.transcript) >= self.max_turns:
            self.ended = True  # her reply used the last turn: the caller should know now
        # 7. Speech: any failure leaves a text-only reply
        audio: bytes | None = None
        try:
            audio = self.speech.speak(spoken)
        except SpeechBudgetUsed:
            notes.append("speech budget used up")
        except Exception as exc:
            notes.append("speech failed: " + safe_error(exc))
        return self._reply(text, goal, notes, audio=audio, rejections=rejections)


if __name__ == "__main__":
    # `python -m natter.live` runs the terminal loop (imported here to avoid a circular import)
    from natter.live_cli import main

    main()
