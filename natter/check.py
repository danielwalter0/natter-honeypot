"""Schema check: the gate between model output and the dossier."""

from dataclasses import dataclass

from natter.schema import STAGE_ORDER, Dossier, Evidence, Stage, Turn


@dataclass(frozen=True)
class Rejection:
    """One fact that was dropped, and why.

    field names the dropped value: the Dossier attribute name for single
    values ("stage", "amount"), or "name[i]" for a list item, where i is the
    item's index in the PROPOSED list ("identifiers[1]").
    """

    field: str
    reason: str


def normalise(text: str) -> str:
    """Collapse any run of whitespace into one space."""
    return " ".join(text.split())


def problem_with(evidence: Evidence, by_index: dict[int, Turn]) -> str | None:
    """Return why this evidence is not acceptable, or None if it is fine."""
    turn = by_index.get(evidence.turn)
    if turn is None:
        return "cited turn does not exist"
    if turn.speaker != "scammer":
        return "cited turn was not spoken by the scammer"
    quote = normalise(evidence.quote)
    if len(quote) < 3:  # the schema's minimum, checked again after normalising
        return "quote is shorter than 3 characters after normalising"
    if not any(char.isalnum() for char in quote):  # only punctuation or invisible characters
        return "quote has no letters or digits"
    if quote not in normalise(turn.text):
        return "quote not found in cited turn"
    return None


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
    6. A quote shorter than 3 characters after whitespace normalisation, or one
       containing no letter or digit, is rejected.

    The proposed object must not be mutated.
    """

    by_index = {turn.index: turn for turn in turns}
    rejections: list[Rejection] = []
    updates: dict[str, object] = {}

    for name in (
        "claimed_organisation",
        "scam_type",
        "stage",
        "payment_method",
        "amount",
        "injection_attempt",
    ):
        item = getattr(proposed, name)
        if item is None:
            continue
        reason = problem_with(item.evidence, by_index)
        if reason is None and name == "stage" and previous_stage is not None:
            if STAGE_ORDER[item.value] < STAGE_ORDER[previous_stage]:
                reason = "stage moved backwards"
        if reason is not None:
            updates[name] = None
            rejections.append(Rejection(name, reason))
    for name in ("identifiers", "pressure_tactics", "information_requested"):
        kept = []
        for position, item in enumerate(getattr(proposed, name)):
            reason = problem_with(item.evidence, by_index)
            if reason is None:
                kept.append(item)
            else:
                rejections.append(Rejection(f"{name}[{position}]", reason))
        updates[name] = kept

    return proposed.model_copy(update=updates), rejections
