"""Tests for odd quotes: too short, blank, invisible or punctuation-only."""

from pathlib import Path

import pytest

from natter.check import check_dossier
from natter.schema import (
    Dossier,
    Evidence,
    Report,
    Sourced,
    Stage,
    Turn,
)

# tests/ is not a package, so the few helpers we need are copied here
EXAMPLE = Path(__file__).parent.parent / "docs" / "example_report.json"
REPORT = Report.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
GOOD = REPORT.dossier
TURNS = REPORT.turns  # scammer speaks on even indexes, persona on odd

SINGLE_FIELDS = [
    "claimed_organisation",
    "scam_type",
    "stage",
    "payment_method",
    "amount",
    "injection_attempt",
]
LIST_FIELDS = ["identifiers", "pressure_tactics", "information_requested"]


def ev(turn: int, quote: str) -> Evidence:
    return Evidence(turn=turn, quote=quote, confidence=0.9)


def org(turn: int, quote: str) -> Sourced[str]:
    return Sourced[str](value="Northbridge Bank", evidence=ev(turn, quote))


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


def reject_org(quote: str, turns: list[Turn] = TURNS) -> None:
    """The organisation quote must be rejected, leaving the field empty."""
    run(
        Dossier(claimed_organisation=org(0, quote)),
        {"claimed_organisation": None},
        ["claimed_organisation"],
        turns=turns,
    )


# ---------------------------------------------------------------- tests


@pytest.mark.parametrize("quote", ["  a  ", " . "], ids=["single-letter", "single-dot"])
def test_tiny_quote_rejected(quote: str) -> None:
    # Too short once whitespace is trimmed, even though it appears in turn 0
    reject_org(quote)


@pytest.mark.parametrize(
    "quote",
    ["   ", "   ", "　　　", "\x1c\x1d\x1e", "\x85\x85\x85", "   "],
    ids=[
        "no-break-space",
        "em-space",
        "ideographic-space",
        "separator-controls",
        "next-line",
        "line-para-separators",
    ],
)
def test_unicode_blank_quote_rejected(quote: str) -> None:
    # Python treats these as whitespace, so they are blank quotes too
    reject_org(quote)


@pytest.mark.parametrize("name", SINGLE_FIELDS + LIST_FIELDS)
def test_blank_quote_rejected_on_every_field(name: str) -> None:
    value = getattr(GOOD, name)
    if name in LIST_FIELDS:
        first = value[0].model_copy(update={"evidence": ev(0, "   ")})
        run(GOOD.model_copy(update={name: [first, *value[1:]]}), {name: value[1:]}, [f"{name}[0]"])
    else:
        bad = value.model_copy(update={"evidence": ev(0, "   ")})
        run(GOOD.model_copy(update={name: bad}), {name: None}, [name], previous=None)


# These lists must match the field lists in natter/check.py. If this test fails,
# a new Dossier field must be added to check_dossier AND here.
def test_checked_fields_cover_dossier() -> None:
    covered = set(SINGLE_FIELDS) | set(LIST_FIELDS) | {"caller_type"}
    assert covered == set(Dossier.model_fields)


def test_invisible_only_quote_rejected() -> None:
    # The quote really is in the turn, but it is only zero-width spaces
    turns = [Turn(index=0, speaker="scammer", text="Hello​​​there from the bank")]
    reject_org("​​​", turns)


def test_punctuation_only_quote_rejected() -> None:
    # Pins the rule that a quote must contain at least one letter or digit
    turns = [Turn(index=0, speaker="scammer", text="Act now!!! Your account is at risk")]
    reject_org("!!!", turns)
