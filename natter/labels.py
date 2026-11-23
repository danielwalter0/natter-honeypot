"""Label validation: catch a mistyped label before scoring, so it is never a silent miss."""

import re
from typing import Any

from natter.schema import IdentifierKind, InfoRequested, PaymentMethod, ScamType, Tactic
from natter.scoring import unwrap

CURRENCY = re.compile(r"[A-Z]{3}")


def words(enum: Any) -> set[str]:
    """The allowed text values of an enum."""
    return {member.value for member in enum}


def is_number(value: Any) -> bool:
    """A real number above zero. bool is excluded (True is an int in Python)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def bad_enum_list(raw: dict[str, Any], name: str, allowed: set[str]) -> bool:
    """True if the field is present but not a list of allowed words."""
    if name not in raw:
        return False
    items = raw[name]
    if not isinstance(items, list):
        return True  # null is invalid too
    return any(unwrap(item) not in allowed for item in items)


def bad_identifier(item: Any) -> bool:
    return (
        not isinstance(item, dict)
        or item.get("kind") not in words(IdentifierKind)
        or not isinstance(item.get("value"), str)
    )


def label_problem(raw: dict[str, Any]) -> str | None:
    """Name of the first bad field in the labels, or None if all are fine."""
    for name in ("is_scam", "injection_attempt"):
        value = unwrap(raw.get(name))
        if value is not None and not isinstance(value, bool):  # "false" and 0 are not bools
            return name
    for name, enum in (("scam_type", ScamType), ("payment_method", PaymentMethod)):
        value = unwrap(raw.get(name))
        if value is not None and value not in words(enum):
            return name
    org = unwrap(raw.get("claimed_organisation"))
    if org is not None and not isinstance(org, str):
        return "claimed_organisation"
    amount = unwrap(raw.get("amount"))
    if amount is not None and not (
        isinstance(amount, dict)
        and is_number(amount.get("amount"))
        and isinstance(amount.get("currency"), str)
        and CURRENCY.fullmatch(amount["currency"])
    ):
        return "amount"
    if "identifiers" in raw and (
        not isinstance(raw["identifiers"], list) or any(map(bad_identifier, raw["identifiers"]))
    ):
        return "identifiers"
    for name, allowed in (
        ("pressure_tactics", words(Tactic)),
        ("information_requested", words(InfoRequested)),
    ):
        if bad_enum_list(raw, name, allowed):
            return name
    return None
