"""Plain-English reason for why the persona did or did not ask a question."""

from natter.picker import Goal, next_goal
from natter.schema import Dossier


def _label(goal: Goal) -> str:
    """Turn CALLBACK_NUMBER into 'callback number'."""
    return goal.value.replace("_", " ")


def goal_reason(
    dossier: Dossier, previous_goal: Goal | None, goal: Goal | None, stalled: bool
) -> str:
    """One sentence saying why she did or did not ask a question this reply."""
    if stalled:
        return "Safe stall: the persona failed, so she used the stock line and asked nothing."
    if goal is not None:
        return f"Asked for {_label(goal)}: the most valuable fact still missing."
    wanted = next_goal(dossier)
    if wanted is None:
        return "No question: every target fact is already in the dossier."
    if previous_goal is not None and wanted == previous_goal:
        return (
            f"No question: she asked for {_label(previous_goal)} last reply, "
            "so she does not repeat herself."
        )
    return "No question this reply."
