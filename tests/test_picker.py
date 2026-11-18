"""Tests for the question picker. Fixtures come from the example report."""

from pathlib import Path

import pytest

from natter.picker import Goal, next_goal
from natter.schema import Dossier, Identifier, IdentifierKind, Report

ROOT = Path(__file__).parent.parent
FULL = Report.model_validate_json(
    (ROOT / "docs" / "example_report.json").read_text(encoding="utf-8")
).dossier


def ident(kind: IdentifierKind) -> Identifier:
    """Pick the example identifier of one kind."""
    return next(i for i in FULL.identifiers if i.kind == kind)


# Facts added one at a time, in priority order
STEPS: list[dict[str, object]] = [
    {"identifiers": [ident(IdentifierKind.PHONE)]},
    {"payment_method": FULL.payment_method},
    {"claimed_organisation": FULL.claimed_organisation},
    {"identifiers": [ident(IdentifierKind.PHONE), ident(IdentifierKind.CASE_REFERENCE)]},
    {"amount": FULL.amount},
]
EXPECTED = [
    Goal.CALLBACK_NUMBER,
    Goal.PAYMENT_METHOD,
    Goal.CLAIMED_ORGANISATION,
    Goal.CASE_REFERENCE,
    Goal.AMOUNT,
    None,
]


def test_empty_dossier_wants_callback_number() -> None:
    assert next_goal(Dossier()) == Goal.CALLBACK_NUMBER


@pytest.mark.parametrize("filled", range(6))
def test_priority_chain(filled: int) -> None:
    update: dict[str, object] = {}
    for step in STEPS[:filled]:
        update.update(step)
    assert next_goal(Dossier().model_copy(update=update)) == EXPECTED[filled]


@pytest.mark.parametrize("kind", [IdentifierKind.ALIAS, IdentifierKind.URL, IdentifierKind.EMAIL])
def test_non_phone_identifier_is_not_callback_number(kind: IdentifierKind) -> None:
    other = ident(IdentifierKind.ALIAS).model_copy(update={"kind": kind})
    assert next_goal(Dossier(identifiers=[other])) == Goal.CALLBACK_NUMBER


def test_case_reference_is_not_callback_number() -> None:
    d = Dossier(identifiers=[ident(IdentifierKind.CASE_REFERENCE)])
    assert next_goal(d) == Goal.CALLBACK_NUMBER


def test_missing_case_reference_is_wanted() -> None:
    # Everything present except the case reference identifier
    others = [i for i in FULL.identifiers if i.kind != IdentifierKind.CASE_REFERENCE]
    d = FULL.model_copy(update={"identifiers": others})
    assert next_goal(d) == Goal.CASE_REFERENCE


@pytest.mark.parametrize("kind", [k for k in IdentifierKind if k != IdentifierKind.PHONE])
def test_every_non_phone_kind_is_not_callback_number(kind: IdentifierKind) -> None:
    other = ident(IdentifierKind.ALIAS).model_copy(update={"kind": kind})
    assert next_goal(Dossier(identifiers=[other])) == Goal.CALLBACK_NUMBER


def test_account_number_is_not_case_reference() -> None:
    # An account number sits where the case reference was, but must not satisfy it
    account = ident(IdentifierKind.CASE_REFERENCE).model_copy(
        update={"kind": IdentifierKind.ACCOUNT_NUMBER}
    )
    others = [i for i in FULL.identifiers if i.kind != IdentifierKind.CASE_REFERENCE]
    d = FULL.model_copy(update={"identifiers": [*others, account]})
    assert next_goal(d) == Goal.CASE_REFERENCE


def test_later_fields_do_not_skip_missing_phone() -> None:
    no_phone = [i for i in FULL.identifiers if i.kind != IdentifierKind.PHONE]
    d = FULL.model_copy(update={"identifiers": no_phone})
    assert next_goal(d) == Goal.CALLBACK_NUMBER


def test_full_dossier_returns_none() -> None:
    assert next_goal(FULL) is None
