import pytest

from natter.goal_reason import goal_reason
from natter.picker import Goal
from natter.schema import (
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    Money,
    PaymentMethod,
    Sourced,
)

EV = Evidence(turn=0, quote="some quote", confidence=0.9)


def full_dossier() -> Dossier:
    """A dossier where all five goals are present."""
    return Dossier(
        claimed_organisation=Sourced(value="Acme Bank", evidence=EV),
        payment_method=Sourced(value=PaymentMethod.GIFT_CARDS, evidence=EV),
        amount=Sourced(value=Money(amount=500, currency="GBP"), evidence=EV),
        identifiers=[
            Identifier(kind=IdentifierKind.PHONE, value="0123456789", evidence=EV),
            Identifier(kind=IdentifierKind.CASE_REFERENCE, value="REF-1", evidence=EV),
        ],
    )


STALL = "Safe stall: the persona failed, so she used the stock line and asked nothing."
DONE = "No question: every target fact is already in the dossier."
OTHER = "No question this reply."


@pytest.mark.parametrize(
    ("dossier", "previous", "goal", "stalled", "expected"),
    [
        (
            Dossier(),
            None,
            Goal.CALLBACK_NUMBER,
            False,
            "Asked for callback number: the most valuable fact still missing.",
        ),
        (
            Dossier(),
            None,
            Goal.CLAIMED_ORGANISATION,
            False,
            "Asked for claimed organisation: the most valuable fact still missing.",
        ),
        (Dossier(), Goal.AMOUNT, Goal.CALLBACK_NUMBER, True, STALL),  # stall beats a goal
        (Dossier(), None, None, True, STALL),
        (full_dossier(), None, None, False, DONE),
        (
            Dossier(),
            Goal.CALLBACK_NUMBER,
            None,
            False,
            "No question: she asked for callback number last reply, "
            "so she does not repeat herself.",
        ),
        (Dossier(), Goal.AMOUNT, None, False, OTHER),  # fallback
        (Dossier(), None, None, False, OTHER),
    ],
)
def test_goal_reason(
    dossier: Dossier, previous: Goal | None, goal: Goal | None, stalled: bool, expected: str
) -> None:
    assert goal_reason(dossier, previous, goal, stalled) == expected


@pytest.mark.parametrize("goal", list(Goal))
def test_every_goal_has_a_label_without_underscore(goal: Goal) -> None:
    text = goal_reason(Dossier(), None, goal, False)
    assert "_" not in text
    assert goal.value.replace("_", " ") in text
