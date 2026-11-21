"""Turns one LiveCall turn into a "frame" that the web page only draws.

Python does all the real work here. The page just renders these fields with
textContent, so nothing is HTML-escaped in this file.
"""

import base64
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from natter.goal_reason import goal_reason
from natter.live import LiveReply
from natter.picker import Goal
from natter.schema import Dossier, Money, Sourced
from natter.session import SessionState


class Bubble(BaseModel):
    """One chat bubble."""

    model_config = ConfigDict(extra="forbid")

    turn: int
    speaker: Literal["scammer", "persona"]
    text: str


class FactRow(BaseModel):
    """One kept dossier value, flat."""

    model_config = ConfigDict(extra="forbid")

    field: str  # "stage", "identifiers[0]", "caller_type" ...
    value: str  # already formatted for display
    turn: int | None  # evidence turn; None only for caller_type
    quote: str | None  # exact evidence quote; None only for caller_type
    confidence: float
    note: str | None = None  # caller_type rationale; else None


class Refusal(BaseModel):
    """One fact the check dropped."""

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str
    turn: int  # scammer turn whose extraction proposed it


class Frame(BaseModel):
    """Everything the page needs to draw one step."""

    model_config = ConfigDict(extra="forbid")

    new_turns: list[Bubble]  # turns added by THIS step only (0, 1 or 2)
    audio: str | None  # "data:audio/wav;base64,..." for this reply, or None
    facts: list[FactRow]  # every kept fact in the current dossier
    refused: list[Refusal]  # EVERY refusal so far in the call, oldest first
    goal: str | None  # goal.value or None
    why_goal: str
    notes: list[str]
    speech_used: int
    speech_cap: int | None  # None in replay (no budget)
    ended: bool
    why: list[str]  # the reviewer "why" strip


def format_value(value: object) -> str:
    """Display text for an enum, bool, Money or str."""
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, bool):  # checked before str/int so True is "yes"
        return "yes" if value else "no"
    if isinstance(value, Money):
        return f"{value.amount:,.2f} {value.currency}"
    return str(value)


def _sourced_row(field: str, sourced: Sourced[Any]) -> FactRow:
    """One row for a value that carries evidence."""
    ev = sourced.evidence
    return FactRow(
        field=field,
        value=format_value(sourced.value),
        turn=ev.turn,
        quote=ev.quote,
        confidence=ev.confidence,
    )


def dossier_rows(dossier: Dossier) -> list[FactRow]:
    """Flatten a dossier into rows, in Dossier field order."""
    rows: list[FactRow] = []
    for name in ("claimed_organisation", "scam_type", "stage", "payment_method", "amount"):
        sourced = getattr(dossier, name)
        if sourced is not None:  # None fields are skipped
            rows.append(_sourced_row(name, sourced))
    for i, ident in enumerate(dossier.identifiers):
        ev = ident.evidence
        rows.append(
            FactRow(
                field=f"identifiers[{i}]",
                value=f"{ident.kind.value}: {ident.value}",
                turn=ev.turn,
                quote=ev.quote,
                confidence=ev.confidence,
            )
        )
    for i, tactic in enumerate(dossier.pressure_tactics):
        rows.append(_sourced_row(f"pressure_tactics[{i}]", tactic))
    for i, info in enumerate(dossier.information_requested):
        rows.append(_sourced_row(f"information_requested[{i}]", info))
    if dossier.injection_attempt is not None:
        rows.append(_sourced_row("injection_attempt", dossier.injection_attempt))
    judged = dossier.caller_type
    if judged is not None:  # a judgement has no turn or quote
        rows.append(
            FactRow(
                field="caller_type",
                value=format_value(judged.value),
                turn=None,
                quote=None,
                confidence=judged.confidence,
                note=judged.rationale,
            )
        )
    return rows


def audio_url(audio: bytes | None) -> str | None:
    """A base64 WAV data URL, or None when there is no audio."""
    if audio is None:
        return None
    return "data:audio/wav;base64," + base64.b64encode(audio).decode("ascii")


def build_frame(
    state: SessionState,
    reply: LiveReply,
    turns_before: int,
    previous_goal: Goal | None,
    speech_cap: int | None,
) -> Frame:
    """Build the frame for one step. Text is passed through unescaped."""
    new_turns = [
        Bubble(turn=t.index, speaker=t.speaker, text=t.text)
        for t in state.transcript[turns_before:]
    ]
    facts = dossier_rows(reply.dossier)
    refused = [
        Refusal(field=r.field, reason=r.reason, turn=t)
        for t, r in zip(state.rejection_turns, state.rejections, strict=True)
    ]
    stalled = any(n.startswith("persona failed") for n in reply.notes)
    if reply.text is None:
        why_goal = "No reply this turn."
    else:
        why_goal = goal_reason(reply.dossier, previous_goal, reply.goal, stalled)

    why = [f"Kept {len(facts)} fact(s), each tied to an exact scammer quote."]
    if reply.rejections:  # drops from this turn
        why += [f"Refused {r.field}: {r.reason}." for r in reply.rejections]
    elif not refused:
        why.append("Refused nothing so far: every proposed fact passed the check.")
    else:
        why.append(f"Refused {len(refused)} fact(s) earlier in the call; none this turn.")
    why.append(why_goal)
    why += [f"Note: {n}." for n in reply.notes]

    return Frame(
        new_turns=new_turns,
        audio=audio_url(reply.audio),
        facts=facts,
        refused=refused,
        goal=reply.goal.value if reply.goal else None,
        why_goal=why_goal,
        notes=reply.notes,
        speech_used=reply.speech_requests_used,
        speech_cap=speech_cap,
        ended=reply.ended,
        why=why,
    )
