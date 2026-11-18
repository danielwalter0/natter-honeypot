"""Tests for the schema check. Most fixtures are built from the example report."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from natter.check import check_dossier
from natter.schema import (
    CallerType,
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    InfoRequested,
    Judgement,
    Report,
    Sourced,
    Stage,
    Tactic,
    Turn,
)

ROOT = Path(__file__).parent.parent
REPORT = Report.model_validate_json(
    (ROOT / "docs" / "example_report.json").read_text(encoding="utf-8")
)
GOOD = REPORT.dossier
TURNS = REPORT.turns  # scammer speaks on even indexes, persona on odd


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
    result, rejections = check_dossier(proposed, turns, previous)
    assert result == proposed.model_copy(update=expect_update)
    assert sorted(r.field for r in rejections) == sorted(rejected)
    assert all(isinstance(r.reason, str) and r.reason for r in rejections)


# ---------------------------------------------------------------- positive


def test_valid_dossier_unchanged() -> None:
    run(GOOD, {}, [])


@pytest.mark.parametrize("quote_in_turn", [False, True])
def test_whitespace_differences_pass(quote_in_turn: bool) -> None:
    messy = "fraud  department\tat\nNorthbridge Bank"  # doubled space, tab, newline
    clean = "fraud department at Northbridge Bank"
    turns = list(TURNS)
    if quote_in_turn:  # mess is in the turn text, quote is clean
        turns[0] = turns[0].model_copy(update={"text": TURNS[0].text.replace(clean, messy)})
        quote = clean
    else:  # mess is in the quote, turn text is clean
        quote = messy
    proposed = Dossier(claimed_organisation=org(0, quote))
    run(proposed, {}, [], turns=turns)


def test_bank_fraud_scenario_passes() -> None:
    folder = ROOT / "scenarios" / "bank-fraud-01"
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    turns = [
        Turn(index=t["turn"], speaker="scammer", text=t["text"]) for t in script["scammer_turns"]
    ]
    expected = Dossier.model_validate_json((folder / "expected.json").read_text(encoding="utf-8"))
    result, rejections = check_dossier(expected, turns, None)
    assert result == expected
    assert rejections == []


def test_caller_type_kept_with_no_turns() -> None:
    judgement = Judgement(value=CallerType.HUMAN, confidence=0.5, rationale="No quote needed.")
    run(Dossier(caller_type=judgement), {}, [], turns=[])


@pytest.mark.parametrize("previous", [None, Stage.HOOK, Stage.PRESSURE, Stage.PAYMENT_ASK])
def test_same_or_earlier_previous_stage_allowed(previous: Stage | None) -> None:
    # GOOD is at payment_ask: forward moves and staying put both pass
    run(GOOD, {}, [], previous=previous)


def test_any_stage_allowed_without_previous() -> None:
    closing = stage(Stage.CLOSING, 8, "you must move £8,500 into a safe account")
    run(Dossier(stage=closing), {}, [], previous=None)


# ---------------------------------------------------------------- negative


def test_quote_from_other_turn_rejected() -> None:
    # Quote is real, but it was said in turn 0, not turn 2
    bad = org(2, "fraud department at Northbridge Bank")
    run(
        GOOD.model_copy(update={"claimed_organisation": bad}),
        {"claimed_organisation": None},
        ["claimed_organisation"],
    )


def test_made_up_quote_rejected() -> None:
    bad = org(0, "head office in Geneva")
    run(
        GOOD.model_copy(update={"claimed_organisation": bad}),
        {"claimed_organisation": None},
        ["claimed_organisation"],
    )


def test_quote_case_must_match() -> None:
    bad = org(0, "northbridge bank")
    run(
        GOOD.model_copy(update={"claimed_organisation": bad}),
        {"claimed_organisation": None},
        ["claimed_organisation"],
    )


def test_missing_turn_rejected() -> None:
    bad = org(99, "fraud department at Northbridge Bank")
    run(
        GOOD.model_copy(update={"claimed_organisation": bad}),
        {"claimed_organisation": None},
        ["claimed_organisation"],
    )


def test_persona_turn_rejected() -> None:
    bad = org(5, "What number can I ring you back on")  # real text, but the persona said it
    run(
        GOOD.model_copy(update={"claimed_organisation": bad}),
        {"claimed_organisation": None},
        ["claimed_organisation"],
    )


def test_backwards_stage_rejected() -> None:
    back = stage(Stage.PRESSURE, 2, "we need to act immediately")  # valid quote
    run(Dossier(stage=back), {"stage": None}, ["stage"], previous=Stage.PAYMENT_ASK)


def test_forward_stage_with_bad_quote_rejected() -> None:
    forward = stage(Stage.PAYMENT_ASK, 8, "send it all in gold bars")
    run(Dossier(stage=forward), {"stage": None}, ["stage"], previous=Stage.HOOK)


def _identifier(e: Evidence) -> Identifier:
    return Identifier(kind=IdentifierKind.ALIAS, value="x", evidence=e)


def _tactic(e: Evidence) -> Sourced[Tactic]:
    return Sourced[Tactic](value=Tactic.URGENCY, evidence=e)


def _info(e: Evidence) -> Sourced[InfoRequested]:
    return Sourced[InfoRequested](value=InfoRequested.PIN, evidence=e)


@pytest.mark.parametrize(
    ("name", "make"),
    [("identifiers", _identifier), ("pressure_tactics", _tactic), ("information_requested", _info)],
)
def test_partial_list_drop_keeps_survivors_in_order(
    name: str, make: Callable[[Evidence], object]
) -> None:
    first, last = ev(0, "this is Mark"), ev(8, "by bank transfer")
    items = [make(first), make(ev(0, "not said anywhere")), make(last)]
    run(Dossier().model_copy(update={name: items}), {name: [items[0], items[2]]}, [f"{name}[1]"])


def test_injection_citing_persona_rejected() -> None:
    fake = Sourced[bool](value=True, evidence=ev(11, "I only have the ones on the kettle"))
    run(
        GOOD.model_copy(update={"injection_attempt": fake}),
        {"injection_attempt": None},
        ["injection_attempt"],
    )
    # The real injection (turn 10) is kept by test_valid_dossier_unchanged


def test_several_failures_each_reported() -> None:
    items = [
        _identifier(ev(0, "nope nope")),
        GOOD.identifiers[1],
        _identifier(ev(99, "this is Mark")),
    ]
    bad_amount = (
        GOOD.amount.model_copy(update={"evidence": ev(8, "£9,999")}) if GOOD.amount else None
    )
    proposed = GOOD.model_copy(
        update={
            "claimed_organisation": org(99, "Northbridge Bank"),
            "amount": bad_amount,
            "identifiers": items,
        }
    )
    update: dict[str, object] = {
        "claimed_organisation": None,
        "amount": None,
        "identifiers": [items[1]],
    }
    run(proposed, update, ["claimed_organisation", "amount", "identifiers[0]", "identifiers[2]"])


def test_proposed_not_mutated() -> None:
    items = [_identifier(ev(0, "nope nope")), GOOD.identifiers[1]]
    proposed = GOOD.model_copy(
        update={"identifiers": items, "claimed_organisation": org(99, "Northbridge")}
    )
    before = proposed.model_dump()
    check_dossier(proposed, TURNS, Stage.HOOK)
    assert proposed.model_dump() == before
