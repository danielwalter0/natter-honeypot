"""Schema check: the gate between model output and the dossier."""

from dataclasses import dataclass

from natter.schema import Dossier, Stage, Turn


@dataclass(frozen=True)
class Rejection:
    """One fact that was dropped, and why.

    field names the dropped value: the Dossier attribute name for single
    values ("stage", "amount"), or "name[i]" for a list item, where i is the
    item's index in the PROPOSED list ("identifiers[1]").
    """

    field: str
    reason: str


def check_dossier(
    proposed: Dossier, turns: list[Turn], previous_stage: Stage | None
) -> tuple[Dossier, list[Rejection]]:
    """Return a copy of proposed holding only facts that pass, plus the drops.

    Rules:
    1. Every evidence quote appears verbatim in the cited turn, after
       whitespace normalisation only. Matching is case-sensitive.
    2. The cited turn must exist (looked up by Turn.index) and its speaker
       must be "scammer".
    3. Stage may not move backwards compared with previous_stage, using
       STAGE_ORDER. previous_stage None allows any stage. The same stage is
       allowed.
    4. caller_type is exempt from these rules (it has no quote).
    5. Fail closed: a failing single-value field becomes None, failing list
       items are dropped, and every drop is reported as a Rejection.

    The proposed object must not be mutated.
    """
    raise NotImplementedError
