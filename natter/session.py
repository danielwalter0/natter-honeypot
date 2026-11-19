"""Session loop: plays scammer lines against a persona and builds a checked dossier."""

from dataclasses import dataclass

from natter.check import Rejection, check_dossier
from natter.picker import next_goal
from natter.providers.base import Extractor, Persona
from natter.schema import Dossier, Turn


@dataclass(frozen=True)
class SessionResult:
    """What a finished session hands back."""

    transcript: list[Turn]  # every turn, scammer and persona, in order
    dossier: Dossier  # latest checked dossier (empty Dossier() if no turns)
    rejections: list[Rejection]  # every drop from every turn, in order
    # rejection_turns[i] is the scammer turn whose extraction dropped rejections[i]
    rejection_turns: list[int]


def snapshot(transcript: list[Turn]) -> list[Turn]:
    """Copy the list AND every Turn in it, so a provider cannot edit the real history."""
    return [turn.model_copy() for turn in transcript]


def run_session(
    scammer_lines: list[str], persona: Persona, extractor: Extractor, max_turns: int
) -> SessionResult:
    """Play each scammer line in order and return the transcript, dossier and drops.

    max_turns caps the TOTAL number of turns (scammer and persona together).
    previous_stage is the last ACCEPTED stage (a Stage), carried across turns,
    so a rejected stage can never reset it to None. It starts as None.
    The final dossier is the latest checked dossier, or Dossier() if there
    were no turns. Rejections from every turn are kept, in order.
    scammer_lines must never be mutated.

    For each scammer line:
    1. Stop if len(transcript) >= max_turns.
    2. Append Turn(index=len(transcript), speaker="scammer", text=line).
    3. proposed = extractor.extract(snapshot(transcript))  (never trusted as is).
    4. dossier, dropped = check_dossier(proposed, transcript, previous_stage)
       and add dropped to the rejections.
    5. If dossier.stage is not None, set previous_stage = dossier.stage.value.
    6. Stop if len(transcript) >= max_turns.
    7. goal = next_goal(dossier); text = persona.reply(snapshot(transcript), goal);
       append Turn(index=len(transcript), speaker="persona", text=text).
    """
    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 0:
        raise ValueError("max_turns must be a whole number, zero or more")
    transcript: list[Turn] = []
    rejections: list[Rejection] = []
    rejection_turns: list[int] = []
    dossier = Dossier()
    previous_stage = None
    for line in scammer_lines:
        if len(transcript) >= max_turns:
            break
        transcript.append(Turn(index=len(transcript), speaker="scammer", text=line))
        proposed = extractor.extract(snapshot(transcript))
        dossier, dropped = check_dossier(proposed, transcript, previous_stage)
        rejections.extend(dropped)
        rejection_turns.extend([len(transcript) - 1] * len(dropped))  # the scammer turn
        if dossier.stage is not None:
            previous_stage = dossier.stage.value
        if len(transcript) >= max_turns:
            break
        goal = next_goal(dossier)
        text = persona.reply(snapshot(transcript), goal)
        transcript.append(Turn(index=len(transcript), speaker="persona", text=text))
    return SessionResult(
        transcript=transcript,
        dossier=dossier,
        rejections=rejections,
        rejection_turns=rejection_turns,
    )
