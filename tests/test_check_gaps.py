"""Extra tests for the schema check: edge cases the first test file does not cover."""

from collections.abc import Callable
from pathlib import Path

import pytest

from natter.check import check_dossier
from natter.schema import (
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    InfoRequested,
    Report,
    Sourced,
    Stage,
    Tactic,
    Turn,
)

# tests/ is not a package, so the few helpers we need are copied here
EXAMPLE = Path(__file__).parent.parent / "docs" / "example_report.json"


def load() -> Report:
    return Report.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


REPORT = load()
GOOD = REPORT.dossier
TURNS = REPORT.turns  # scammer speaks on even indexes, persona on odd
MADE_UP = "something nobody ever said"


def ev(turn: int, quote: str) -> Evidence:
    return Evidence(turn=turn, quote=quote, confidence=0.9)


def org(turn: int, quote: str) -> Sourced[str]:
    return Sourced[str](value="Northbridge Bank", evidence=ev(turn, quote))


def stage(value: Stage, turn: int, quote: str) -> Sourced[Stage]:
    return Sourced[Stage](value=value, evidence=ev(turn, quote))


def run(
    proposed: Dossier,
    expect_update: dict[str, object],
    rejected: list[str],
    previous: Stage | None = None,
    turns: list[Turn] = TURNS,
) -> None:
    """Check the result equals proposed with expect_update applied, and the rejected fields."""
    before = proposed.model_dump()  # snapshot so we can prove the input is not mutated
    expected = proposed.model_copy(update=expect_update)  # built before the call on purpose
    result, rejections = check_dossier(proposed, turns, previous)
    assert proposed.model_dump() == before
    assert result == expected
    assert sorted(r.field for r in rejections) == sorted(rejected)
    assert all(isinstance(r.reason, str) and r.reason for r in rejections)


def _identifier(e: Evidence) -> Identifier:
    return Identifier(kind=IdentifierKind.ALIAS, value="x", evidence=e)


def _tactic(e: Evidence) -> Sourced[Tactic]:
    return Sourced[Tactic](value=Tactic.URGENCY, evidence=e)


def _info(e: Evidence) -> Sourced[InfoRequested]:
    return Sourced[InfoRequested](value=InfoRequested.PIN, evidence=e)


LIST_CASES = [
    ("identifiers", _identifier),
    ("pressure_tactics", _tactic),
    ("information_requested", _info),
]

# ---------------------------------------------------------------- tests


@pytest.mark.parametrize("quote", ["   ", "\t\n ", " \n  "])
def test_blank_quote_rejected(quote: str) -> None:
    # A blank quote is "found" in any text by a naive substring test, so it must fail
    bad = org(0, quote)
    run(Dossier(claimed_organisation=bad), {"claimed_organisation": None}, ["claimed_organisation"])


@pytest.mark.parametrize(
    "name",
    ["claimed_organisation", "scam_type", "stage", "payment_method", "amount", "injection_attempt"],
)
def test_every_single_field_checked(name: str) -> None:
    field = getattr(GOOD, name)
    bad = field.model_copy(update={"evidence": ev(0, MADE_UP)})  # real scammer turn, fake quote
    run(GOOD.model_copy(update={name: bad}), {name: None}, [name], previous=None)


def test_proposed_not_mutated_with_messy_and_failing_input() -> None:
    messy = "fraud  department\tat  Northbridge   Bank"  # valid once whitespace is normalised
    items = [_identifier(ev(0, MADE_UP)), GOOD.identifiers[1]]
    proposed = GOOD.model_copy(update={"claimed_organisation": org(0, messy), "identifiers": items})
    before = proposed.model_dump()
    result, rejections = check_dossier(proposed, TURNS, Stage.HOOK)
    assert proposed.model_dump() == before
    assert [r.field for r in rejections] == ["identifiers[0]"]
    assert result.claimed_organisation == proposed.claimed_organisation
    assert GOOD == load().dossier  # the shared fixture was not changed either


def test_removed_space_rejected() -> None:
    # Whitespace may be collapsed but never removed
    bad = org(0, "frauddepartment at Northbridge Bank")
    run(Dossier(claimed_organisation=bad), {"claimed_organisation": None}, ["claimed_organisation"])


def test_removed_comma_rejected() -> None:
    # Punctuation is not normalised away: "£8500" is not "£8,500"
    assert GOOD.amount is not None
    bad = GOOD.amount.model_copy(update={"evidence": ev(8, "£8500")})
    run(Dossier(amount=bad), {"amount": None}, ["amount"])


def test_fullwidth_identifier_rejected() -> None:
    # Fullwidth letters look the same but are different characters: no Unicode folding
    fake = Identifier(
        kind=IdentifierKind.CASE_REFERENCE, value="NB-4471", evidence=ev(6, "ＮＢ-4471")
    )
    run(Dossier(identifiers=[fake]), {"identifiers": []}, ["identifiers[0]"])


def test_missing_stage_with_previous_stage() -> None:
    run(Dossier(), {}, [], previous=Stage.PAYMENT_ASK)


@pytest.mark.parametrize(
    ("previous", "proposed_stage"),
    [
        (Stage.CLOSING, Stage.HOOK),
        (Stage.PRESSURE, Stage.HOOK),
        (Stage.PAYMENT_ASK, Stage.PRESSURE),
    ],
)
def test_backwards_stage_rejected_pairs(previous: Stage, proposed_stage: Stage) -> None:
    back = stage(proposed_stage, 2, "we need to act immediately")  # valid quote
    run(Dossier(stage=back), {"stage": None}, ["stage"], previous=previous)


def test_forward_to_closing_kept() -> None:
    closing = stage(Stage.CLOSING, 2, "we need to act immediately")
    run(Dossier(stage=closing), {}, [], previous=Stage.PAYMENT_ASK)


@pytest.mark.parametrize(("name", "make"), LIST_CASES)
def test_partial_list_drop_with_persona_item(name: str, make: Callable[[Evidence], object]) -> None:
    items = [
        make(ev(0, "this is Mark")),
        make(ev(0, MADE_UP)),  # index 1: made-up quote
        make(ev(8, "by bank transfer")),
        make(ev(5, "What number can I ring you back on")),  # index 3: persona turn
    ]
    run(
        Dossier().model_copy(update={name: items}),
        {name: [items[0], items[2]]},
        [f"{name}[1]", f"{name}[3]"],
    )


def test_backwards_stage_with_bad_quote_one_rejection() -> None:
    # Two things are wrong (backwards and fake quote) but only one rejection is reported
    bad = stage(Stage.PRESSURE, 2, MADE_UP)
    result, rejections = check_dossier(Dossier(stage=bad), TURNS, Stage.PAYMENT_ASK)
    assert result.stage is None
    assert [r.field for r in rejections] == ["stage"]
    assert rejections[0].reason
