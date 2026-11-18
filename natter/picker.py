"""Question picker: choose the most valuable fact still missing."""

from enum import StrEnum

from natter.schema import Dossier


class Goal(StrEnum):
    CALLBACK_NUMBER = "callback_number"
    PAYMENT_METHOD = "payment_method"
    CLAIMED_ORGANISATION = "claimed_organisation"
    CASE_REFERENCE = "case_reference"
    AMOUNT = "amount"


def next_goal(dossier: Dossier) -> Goal | None:
    """Return the highest-priority goal that is still missing, or None.

    Priority is the order of the Goal members above. A goal counts as present
    when:
    - CALLBACK_NUMBER: any identifier has kind PHONE
    - CASE_REFERENCE: any identifier has kind CASE_REFERENCE
    - PAYMENT_METHOD, CLAIMED_ORGANISATION, AMOUNT: the field is not None
    Return None when every goal is present.
    """
    raise NotImplementedError
