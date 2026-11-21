"""Session loop: plays scammer lines against a persona and builds a checked dossier."""

from dataclasses import dataclass, field

from natter.check import Rejection, check_dossier
from natter.picker import Goal, next_goal
from natter.providers.base import Extractor, Persona
from natter.schema import Dossier, Stage, Turn


@dataclass(frozen=True)
class SessionResult:
    """What a finished session hands back."""

    transcript: list[Turn]  # every turn, scammer and persona, in order
    dossier: Dossier  # latest checked dossier (empty Dossier() if no turns)
    rejections: list[Rejection]  # every drop from every turn, in order
    # rejection_turns[i] is the scammer turn whose extraction dropped rejections[i]
    rejection_turns: list[int]
    # goals[i] is the goal given to persona reply i (None: nothing left to ask, or a stall turn)
    goals: list[Goal | None]


def snapshot(transcript: list[Turn]) -> list[Turn]:
    """Copy the list AND every Turn in it, so a provider cannot edit the real history."""
    return [turn.model_copy() for turn in transcript]


@dataclass
class SessionState:
    """Everything a running session remembers. Mutable: the step functions edit it."""

    transcript: list[Turn] = field(default_factory=list)
    dossier: Dossier = field(default_factory=Dossier)  # latest checked dossier
    previous_stage: Stage | None = None  # last ACCEPTED stage value, never reset by a drop
    previous_goal: Goal | None = None  # goal given on the last reply (None after a stall)
    rejections: list[Rejection] = field(default_factory=list)
    rejection_turns: list[int] = field(default_factory=list)  # scammer turn of each rejection
    goals: list[Goal | None] = field(default_factory=list)  # one per persona reply


def add_scammer_line(state: SessionState, line: str) -> None:
    """Append the scammer's line as the next turn."""
    state.transcript.append(Turn(index=len(state.transcript), speaker="scammer", text=line))


def apply_extraction(state: SessionState, proposed: Dossier) -> list[Rejection]:
    """Check the proposed dossier against the transcript and keep what passes.

    Returns only THIS call's drops. The latest turn must be the scammer turn.
    """
    # Work out everything first; state is only touched at the end, so a failure changes nothing
    dossier, dropped = check_dossier(proposed, state.transcript, state.previous_stage)
    new_stage = state.previous_stage
    if dossier.stage is not None:
        new_stage = dossier.stage.value  # only accepted stages are carried
    state.dossier = dossier
    state.rejections.extend(dropped)
    state.rejection_turns.extend([len(state.transcript) - 1] * len(dropped))
    state.previous_stage = new_stage
    return dropped


def choose_goal(state: SessionState) -> Goal | None:
    """Return next_goal(state.dossier), or None if that equals state.previous_goal.

    She never asks for the same thing two replies running. Changes nothing in state.
    """
    goal = next_goal(state.dossier)
    if goal == state.previous_goal:
        return None
    return goal


def add_persona_reply(state: SessionState, goal: Goal | None, text: str) -> None:
    """Record the persona's reply: append its Turn and the goal, and remember the goal.

    previous_goal = goal, so a stall (goal=None) resets the no-repeat rule.
    """
    state.transcript.append(Turn(index=len(state.transcript), speaker="persona", text=text))
    state.goals.append(goal)
    state.previous_goal = goal


def run_session(
    scammer_lines: list[str], persona: Persona, extractor: Extractor, max_turns: int
) -> SessionResult:
    """Play each scammer line in order and return the transcript, dossier and drops.

    max_turns caps the TOTAL number of turns (scammer and persona together).
    The final dossier is the latest checked dossier, or Dossier() if there
    were no turns. Rejections from every turn are kept, in order.
    scammer_lines must never be mutated. Provider errors propagate.

    For each scammer line:
    1. Stop if len(transcript) >= max_turns.
    2. add_scammer_line appends the scammer turn.
    3. extractor.extract(snapshot(transcript)) is never trusted as is.
    4. apply_extraction checks it, keeps the dossier, logs the drops and
       carries the last accepted stage forward.
    5. Stop if len(transcript) >= max_turns.
    6. choose_goal picks the goal (None if it repeats the last one).
       persona.reply(snapshot(transcript), goal) gives the text, and
       add_persona_reply records the turn, the goal and previous_goal.
    """
    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 0:
        raise ValueError("max_turns must be a whole number, zero or more")
    state = SessionState()
    for line in scammer_lines:
        if len(state.transcript) >= max_turns:
            break
        add_scammer_line(state, line)
        apply_extraction(state, extractor.extract(snapshot(state.transcript)))
        if len(state.transcript) >= max_turns:
            break
        goal = choose_goal(state)
        text = persona.reply(snapshot(state.transcript), goal)
        add_persona_reply(state, goal, text)
    return SessionResult(
        transcript=state.transcript,
        dossier=state.dossier,
        rejections=state.rejections,
        rejection_turns=state.rejection_turns,
        goals=state.goals,
    )
