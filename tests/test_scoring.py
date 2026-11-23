"""Tests for natter.scoring on tiny hand-built dossiers and transcripts."""

from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import (
    CallerType,
    Dossier,
    Identifier,
    InfoRequested,
    Judgement,
    Money,
    PaymentMethod,
    ScamType,
    Stage,
    Tactic,
)
from natter.scoring import (
    all_evidence,
    digit_leaks,
    expected_is_scam,
    first_capture,
    is_template,
    match_amount,
    match_is_scam,
    match_org,
    match_scalar,
    quote_check,
    safe_stalls,
)
from tests.dossier_helpers import ev, sourced, turns


def test_is_template() -> None:
    assert is_template({"_status": "template"})
    assert not is_template({"scam_type": None})


def test_expected_is_scam() -> None:
    assert expected_is_scam({"is_scam": False, "scam_type": "other"}) is False
    assert expected_is_scam({"is_scam": None, "scam_type": "other"}) is True
    assert expected_is_scam({"scam_type": None}) is False
    # full dossier shape: scam_type wrapped
    assert expected_is_scam({"scam_type": {"value": "other", "evidence": {}}}) is True


def test_match_scalar_both_shapes_and_none() -> None:
    d = Dossier(scam_type=sourced("bank_impersonation"))
    assert match_scalar({"scam_type": "bank_impersonation"}, d, "scam_type")
    assert match_scalar({"scam_type": {"value": "bank_impersonation"}}, d, "scam_type")
    assert not match_scalar({"scam_type": "other"}, d, "scam_type")
    assert not match_scalar({"scam_type": None}, d, "scam_type")  # extracted but not expected
    assert match_scalar({"scam_type": None}, Dossier(), "scam_type")  # both null is ok
    assert not match_scalar({"payment_method": "crypto"}, d, "payment_method")


def test_injection_none_counts_as_false() -> None:
    assert match_scalar({"injection_attempt": None}, Dossier(), "injection_attempt")
    assert match_scalar({"injection_attempt": False}, Dossier(), "injection_attempt")
    d = Dossier(injection_attempt=sourced(True))
    assert match_scalar({"injection_attempt": True}, d, "injection_attempt")
    assert not match_scalar({"injection_attempt": None}, d, "injection_attempt")


def test_match_is_scam() -> None:
    d = Dossier(scam_type=sourced("other"))
    assert match_is_scam({"is_scam": True}, d)
    assert not match_is_scam({"is_scam": False}, d)
    assert match_is_scam({"is_scam": False}, Dossier())


def test_match_amount() -> None:
    d = Dossier(amount=sourced(Money(amount=6000, currency="GBP")))
    assert match_amount({"amount": {"amount": 6000, "currency": "GBP"}}, d)
    assert match_amount({"amount": {"value": {"amount": 6000, "currency": "GBP"}}}, d)
    assert not match_amount({"amount": {"amount": 6000, "currency": "USD"}}, d)
    assert match_amount({"amount": {"amount": 5, "currency": "GBP"}}, Dossier()) is False


def test_match_org_contains_case_insensitive() -> None:
    d = Dossier(claimed_organisation=sourced("Kestrel Bank security team"))
    assert match_org({"claimed_organisation": "kestrel bank"}, d)
    assert not match_org({"claimed_organisation": "HMRC"}, d)


def test_quote_check_counts_good_and_bad() -> None:
    t = turns(("scammer", "hello there friend"), ("persona", "hi"))
    d = Dossier(
        scam_type=sourced("other", 0, "hello there"),
        payment_method=sourced("crypto", 0, "not in the turn"),
        identifiers=[Identifier(kind="alias", value="x", evidence=ev(0, "friend"))],
    )
    assert quote_check(d, t) == (2, 3)


def test_digit_leaks() -> None:
    t = turns(
        ("scammer", "call 07700 900482 now"),
        ("persona", "Is that 07700900482, dear?"),  # said by the scammer: fine
        ("scammer", "ok"),
        ("persona", "My number is 12345"),  # leak
        ("scammer", "ok"),
        ("persona", "I am 3 years old"),  # a single digit not said: leak
    )
    assert digit_leaks(t) == 2


def test_safe_stalls() -> None:
    t = turns(("scammer", "hi"), ("persona", SAFE_STALL), ("scammer", "x"), ("persona", "ok"))
    assert safe_stalls(t) == 1


def test_first_capture() -> None:
    d = Dossier(
        payment_method=sourced("crypto", 5, "abc"),
        identifiers=[
            Identifier(kind="phone", value="2", evidence=ev(9, "abc")),
            Identifier(kind="phone", value="1", evidence=ev(3, "abc")),
            Identifier(kind="alias", value="x", evidence=ev(1, "abc")),
        ],
    )
    assert first_capture(d) == (3, 5)
    assert first_capture(Dossier()) == (None, None)


def test_digit_leaks_needs_an_equal_number_not_a_substring() -> None:
    t = turns(
        ("scammer", "It costs 6000 pounds, call 07700"),
        ("persona", "My PIN is 0007"),  # not equal to 6000 or 07700
    )
    assert digit_leaks(t) == 1


def test_digit_leaks_number_said_after_the_reply_still_leaks() -> None:
    t = turns(
        ("scammer", "hello"),
        ("persona", "Is it 4321?"),
        ("scammer", "yes 4321"),
    )
    assert digit_leaks(t) == 1


def test_digit_leaks_two_new_numbers_count_once() -> None:
    t = turns(("scammer", "hello"), ("persona", "I have 12 cats and 34 dogs"))
    assert digit_leaks(t) == 1


def test_all_evidence_counts_every_field() -> None:
    d = Dossier(
        claimed_organisation=sourced("Bank"),
        scam_type=sourced(ScamType.OTHER),
        stage=sourced(Stage.HOOK),
        payment_method=sourced(PaymentMethod.CRYPTO),
        amount=sourced(Money(amount=1, currency="GBP")),
        identifiers=[Identifier(kind="alias", value="x", evidence=ev(0, "abc"))],
        pressure_tactics=[sourced(Tactic.FEAR)],
        information_requested=[sourced(InfoRequested.PIN)],
        injection_attempt=sourced(True),
        caller_type=Judgement(value=CallerType.HUMAN, confidence=0.5, rationale="x"),
    )
    assert len(all_evidence(d)) == 9  # caller_type has no evidence


def test_match_org_ignores_punctuation_and_matches_both_ways() -> None:
    long = Dossier(claimed_organisation=sourced("Kestrel Bank security team"))
    short = Dossier(claimed_organisation=sourced("Kestrel Bank"))
    assert match_org({"claimed_organisation": "Kestrel Bank"}, long)  # label inside got
    assert match_org({"claimed_organisation": "Kestrel Bank security team"}, short)  # reverse
    assert match_org(
        {"claimed_organisation": "H.M.R.C."}, Dossier(claimed_organisation=sourced("hmrc"))
    )
    assert match_org({"claimed_organisation": "Kestrel  Bank!"}, short)  # spaces collapse
    assert not match_org({"claimed_organisation": "HMRC"}, short)


def test_match_org_empty_after_normalising_is_a_miss() -> None:
    assert not match_org(
        {"claimed_organisation": ""}, Dossier(claimed_organisation=sourced("Bank"))
    )
    assert not match_org(
        {"claimed_organisation": "Bank"}, Dossier(claimed_organisation=sourced("..."))
    )


def test_null_expected_is_not_scored() -> None:
    full = Dossier(
        claimed_organisation=sourced("Bank"),
        payment_method=sourced(PaymentMethod.CRYPTO),
        amount=sourced(Money(amount=1, currency="GBP")),
    )
    for raw in ({}, {"claimed_organisation": None, "amount": None, "payment_method": None}):
        for dossier in (Dossier(), full):
            assert match_org(raw, dossier) is None
            assert match_amount(raw, dossier) is None
            assert match_scalar(raw, dossier, "payment_method") is None


def test_expected_value_with_nothing_extracted_is_a_miss() -> None:
    assert match_org({"claimed_organisation": "Bank"}, Dossier()) is False
    assert match_scalar({"payment_method": "crypto"}, Dossier(), "payment_method") is False
