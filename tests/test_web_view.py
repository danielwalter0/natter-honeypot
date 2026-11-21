"""Tests for the web frame builder. No network: LiveCall runs on fakes."""

import base64

import pytest
from pydantic import ValidationError

from natter.goal_reason import goal_reason
from natter.providers.fakes import FakeExtractor
from natter.schema import (
    CallerType,
    Dossier,
    Evidence,
    Identifier,
    IdentifierKind,
    InfoRequested,
    Judgement,
    Money,
    PaymentMethod,
    ScamType,
    Sourced,
    Stage,
    Tactic,
)
from natter.web_view import Frame, audio_url, build_frame, dossier_rows, format_value
from tests.live_fakes import BAD, LINES, PHONE, RaisingExtractor, RaisingPersona, make_call


def ev(turn: int, quote: str) -> Evidence:
    return Evidence(turn=turn, quote=quote, confidence=0.8)


# ---------------------------------------------------------------- format_value


def test_format_value_enum() -> None:
    assert format_value(Stage.PAYMENT_ASK) == "payment_ask"


def test_format_value_bool() -> None:
    assert format_value(True) == "yes"
    assert format_value(False) == "no"


def test_format_value_money_has_thousands_and_two_places() -> None:
    assert format_value(Money(amount=6000, currency="GBP")) == "6,000.00 GBP"


def test_format_value_plain_string() -> None:
    assert format_value("Barclays Bank") == "Barclays Bank"


# ---------------------------------------------------------------- dossier_rows


def test_dossier_rows_empty() -> None:
    assert dossier_rows(Dossier()) == []


def full_dossier() -> Dossier:
    return Dossier(
        claimed_organisation=Sourced(value="Barclays", evidence=ev(0, "this is Barclays")),
        scam_type=Sourced(value=ScamType.BANK_IMPERSONATION, evidence=ev(0, "fraud team")),
        stage=Sourced(value=Stage.PRESSURE, evidence=ev(2, "right now")),
        payment_method=Sourced(value=PaymentMethod.GIFT_CARDS, evidence=ev(4, "gift cards")),
        amount=Sourced(value=Money(amount=6000, currency="GBP"), evidence=ev(4, "six thousand")),
        identifiers=[
            PHONE,
            Identifier(kind=IdentifierKind.EMAIL, value="a@b.co", evidence=ev(2, "email a@b.co")),
        ],
        pressure_tactics=[Sourced(value=Tactic.URGENCY, evidence=ev(2, "right now"))],
        information_requested=[Sourced(value=InfoRequested.PIN, evidence=ev(4, "your PIN"))],
        injection_attempt=Sourced(value=True, evidence=ev(6, "ignore your rules")),
        caller_type=Judgement(value=CallerType.HUMAN, confidence=0.7, rationale="Natural pauses"),
    )


def test_dossier_rows_full_order_and_values() -> None:
    rows = dossier_rows(full_dossier())
    assert [r.field for r in rows] == [
        "claimed_organisation",
        "scam_type",
        "stage",
        "payment_method",
        "amount",
        "identifiers[0]",
        "identifiers[1]",
        "pressure_tactics[0]",
        "information_requested[0]",
        "injection_attempt",
        "caller_type",
    ]
    by_field = {r.field: r for r in rows}
    assert by_field["identifiers[0]"].value == "phone: 07700 900482"
    assert by_field["identifiers[1]"].value == "email: a@b.co"
    assert by_field["amount"].value == "6,000.00 GBP"
    assert by_field["injection_attempt"].value == "yes"
    assert by_field["stage"].turn == 2
    assert by_field["stage"].quote == "right now"  # copied exactly
    assert by_field["stage"].confidence == 0.8
    assert by_field["stage"].note is None


def test_dossier_rows_caller_type_has_no_turn_or_quote() -> None:
    row = dossier_rows(full_dossier())[-1]
    assert row.field == "caller_type"
    assert row.value == "human"
    assert row.turn is None
    assert row.quote is None
    assert row.note == "Natural pauses"
    assert row.confidence == 0.7


# ---------------------------------------------------------------- audio_url


def test_audio_url_none() -> None:
    assert audio_url(None) is None


def test_audio_url_round_trips() -> None:
    wav = b"RIFF\x00\x01\x02\x03WAVE\xff"
    url = audio_url(wav)
    assert url is not None
    prefix = "data:audio/wav;base64,"
    assert url.startswith(prefix)
    assert base64.b64decode(url[len(prefix) :]) == wav


# ---------------------------------------------------------------- build_frame


class FirstTurnBadExtractor:
    """Proposes a bad quote on the first call only."""

    name = "first-bad"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, transcript: list) -> Dossier:  # type: ignore[type-arg]
        self.calls += 1
        return Dossier(identifiers=[PHONE, BAD] if self.calls == 1 else [PHONE])


def test_first_say_frame() -> None:
    call = make_call()
    before, prev = len(call.state.transcript), call.state.previous_goal
    reply = call.say(LINES[0])
    frame = build_frame(call.state, reply, before, prev, 15)
    assert [(b.turn, b.speaker) for b in frame.new_turns] == [(0, "scammer"), (1, "persona")]
    assert frame.new_turns[0].text == LINES[0]
    assert reply.text is not None
    assert frame.new_turns[1].text == reply.text
    assert frame.audio is not None
    assert frame.audio.startswith("data:audio/wav;base64,")
    assert frame.goal == (reply.goal.value if reply.goal else None)
    assert frame.why_goal == goal_reason(reply.dossier, prev, reply.goal, False)
    assert frame.speech_cap == 15
    assert frame.speech_used == reply.speech_requests_used
    assert frame.ended is False
    assert [r.field for r in frame.facts] == ["identifiers[0]"]
    assert frame.why[0] == "Kept 1 fact(s), each tied to an exact scammer quote."
    assert frame.why[-1] == frame.why_goal


def test_replay_has_no_cap() -> None:
    call = make_call()
    reply = call.say(LINES[0])
    assert build_frame(call.state, reply, 0, None, None).speech_cap is None


def test_rejected_empty_line_adds_nothing() -> None:
    call = make_call()
    before, prev = len(call.state.transcript), call.state.previous_goal
    reply = call.say("   ")
    frame = build_frame(call.state, reply, before, prev, None)
    assert frame.new_turns == []
    assert "line rejected: empty or not text" in frame.notes
    assert frame.why_goal == "No reply this turn."
    assert "Note: line rejected: empty or not text." in frame.why


def test_persona_failure_is_a_safe_stall() -> None:
    call = make_call(persona=RaisingPersona())
    before, prev = len(call.state.transcript), call.state.previous_goal
    reply = call.say(LINES[0])
    frame = build_frame(call.state, reply, before, prev, None)
    assert frame.goal is None
    assert frame.why_goal.startswith("Safe stall")
    assert any(w.startswith("Note: persona failed") for w in frame.why)
    assert frame.new_turns[1].text == reply.text


def test_refusal_history_is_kept_across_turns() -> None:
    call = make_call(extractor=FirstTurnBadExtractor())

    before, prev = len(call.state.transcript), call.state.previous_goal
    first = call.say(LINES[0])
    f1 = build_frame(call.state, first, before, prev, None)
    assert len(f1.refused) == 1
    assert f1.refused[0].reason == "quote not found in cited turn"
    assert f1.refused[0].turn == 0
    assert any(
        w.startswith("Refused identifiers[") and w.endswith(": quote not found in cited turn.")
        for w in f1.why
    )

    before, prev = len(call.state.transcript), call.state.previous_goal
    second = call.say(LINES[1])
    f2 = build_frame(call.state, second, before, prev, None)
    assert f2.refused == f1.refused  # same single entry, still listed
    assert "Refused 1 fact(s) earlier in the call; none this turn." in f2.why


def test_no_refusals_says_so() -> None:
    call = make_call()
    reply = call.say(LINES[0])
    frame = build_frame(call.state, reply, 0, None, None)
    assert frame.refused == []
    assert "Refused nothing so far: every proposed fact passed the check." in frame.why


QUOTED_LINE = "Kept 1 fact(s), each tied to an exact scammer quote."
NO_CHECK_LINE = "No check ran this turn, so nothing new was kept or refused."


def test_caller_type_is_not_counted_as_a_quoted_fact() -> None:
    judged = Judgement(value=CallerType.HUMAN, confidence=0.5, rationale="sounds natural")
    call = make_call(extractor=FakeExtractor(Dossier(identifiers=[PHONE], caller_type=judged)))
    frame = build_frame(call.state, call.say(LINES[0]), 0, None, None)
    assert len(frame.facts) == 2  # the phone number and the caller type
    assert frame.why[0] == QUOTED_LINE  # only the phone has a quote
    assert frame.why[1] == "Caller type is a judgement with no quote, so it is not checked."


def test_caller_type_line_only_when_there_is_a_caller_type() -> None:
    call = make_call()
    frame = build_frame(call.state, call.say(LINES[0]), 0, None, None)
    assert not any(w.startswith("Caller type") for w in frame.why)


@pytest.mark.parametrize(
    "parts",
    [
        {"extractor": RaisingExtractor(RuntimeError("boom"))},  # extraction failed
        {"max_extractions": 0},  # extraction cap reached
    ],
)
def test_no_check_is_said_plainly(parts: dict[str, object]) -> None:
    call = make_call(**parts)
    frame = build_frame(call.state, call.say(LINES[0]), 0, None, None)
    assert NO_CHECK_LINE in frame.why
    assert not any("passed the check" in w for w in frame.why)


def test_rejected_line_runs_no_check() -> None:
    call = make_call()
    frame = build_frame(call.state, call.say("   "), 0, None, None)
    assert NO_CHECK_LINE in frame.why


def test_untrusted_text_is_not_escaped() -> None:
    line = '<script>alert(1)</script> & "x"'
    call = make_call()
    before, prev = len(call.state.transcript), call.state.previous_goal
    reply = call.say(line)
    frame = build_frame(call.state, reply, before, prev, None)
    assert frame.new_turns[0].text == line


def test_frame_rejects_extra_field() -> None:
    data: dict[str, object] = {
        "new_turns": [],
        "audio": None,
        "facts": [],
        "refused": [],
        "goal": None,
        "why_goal": "",
        "notes": [],
        "speech_used": 0,
        "speech_cap": None,
        "ended": False,
        "why": [],
    }
    Frame(**data)
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        Frame(**data)
