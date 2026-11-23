"""Tests for natter.eval_details (formatting only) and one real no-keys run."""

from natter.__main__ import ROOT
from natter.check import Rejection
from natter.eval_details import (
    details_text,
    identifier_diff,
    rejection_lines,
    string_diff,
    transcript_lines,
)
from natter.evaluate import replay_scenario, replay_session
from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import Dossier, Identifier, IdentifierKind
from tests.dossier_helpers import ev, sourced, turns


def phone(value: str) -> Identifier:
    return Identifier(kind=IdentifierKind.PHONE, value=value, evidence=ev(0, "abc"))


def test_identifier_diff_uses_the_scoring_match() -> None:
    raw = {
        "identifiers": [
            {"kind": "phone", "value": "07700-900482"},  # matched by the extracted phone
            {"kind": "alias", "value": "James Carter"},  # missed
        ]
    }
    d = Dossier(
        identifiers=[
            phone("07700 900482"),
            Identifier(kind=IdentifierKind.URL, value="http://bad.example", evidence=ev(0, "abc")),
        ]
    )
    missed, extra = identifier_diff(raw, d)
    assert missed == ["alias: James Carter"]  # shown as written in the label
    assert extra == ["url: http://bad.example"]


def test_identifier_diff_empty() -> None:
    assert identifier_diff({"identifiers": []}, Dossier()) == ([], [])


def test_string_diff_plain_equality_both_shapes() -> None:
    raw = {"pressure_tactics": ["fear", {"value": "urgency", "evidence": {}}]}
    d = Dossier(pressure_tactics=[sourced("fear"), sourced("secrecy")])
    assert string_diff(raw, d, "pressure_tactics") == (["urgency"], ["secrecy"])


def test_rejection_lines() -> None:
    rejections = [Rejection("identifiers[1]", "quote not found in cited turn")]
    assert rejection_lines(rejections, [4]) == [
        "turn 4, identifiers[1]: quote not found in cited turn"
    ]
    assert rejection_lines([], []) == ["none"]


def test_transcript_lines_mark_safe_stalls() -> None:
    t = turns(("scammer", "hello"), ("persona", SAFE_STALL), ("scammer", "x"), ("persona", "ok"))
    assert transcript_lines(t) == [
        "[0] scammer: hello",
        f"[1] persona: {SAFE_STALL} [safe stall]",
        "[2] scammer: x",
        "[3] persona: ok",
    ]


def test_details_text_shows_none_for_empty_lists() -> None:
    text = details_text("a-01", {}, Dossier(), [], [])
    assert text.splitlines()[0] == "## a-01"
    assert "identifiers missed: none" in text
    assert "pressure_tactics extra: none" in text
    assert "rejections: none" in text


def test_real_bank_fraud_01_details_and_transcript_without_keys() -> None:
    folder = ROOT / "scenarios" / "bank-fraud-01"
    outcome = replay_scenario(folder)
    assert outcome.status == "scored" and outcome.result is not None
    result = outcome.result
    text = details_text(
        folder.name, outcome.raw, result.dossier, result.rejections, result.rejection_turns
    )
    assert text.startswith("## bank-fraud-01")
    lines = transcript_lines(replay_session(folder).transcript)
    assert lines[0].startswith("[0] scammer: ")
    for line, turn in zip(lines, result.transcript, strict=True):
        assert line.endswith("[safe stall]") == (
            turn.speaker == "persona" and turn.text == SAFE_STALL
        )
