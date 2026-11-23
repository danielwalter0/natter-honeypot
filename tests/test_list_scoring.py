"""Tests for natter.list_scoring: identifiers, tactics and info lists."""

from natter.list_scoring import precision_recall, score_identifiers, score_string_list
from natter.schema import Dossier, Identifier, IdentifierKind
from tests.dossier_helpers import ev, sourced


def test_precision_recall() -> None:
    assert precision_recall({"a", "b"}, {"a", "c"}) == (0.5, 0.5)
    assert precision_recall(set(), set()) == (1.0, 1.0)
    assert precision_recall({"a"}, set()) == (1.0, 0.0)
    assert precision_recall(set(), {"a"}) == (0.0, 1.0)


def test_score_identifiers_ignores_spaces_and_case() -> None:
    raw = {"identifiers": [{"kind": "phone", "value": "07700 900482"}]}
    d = Dossier(identifiers=[Identifier(kind="phone", value="07700900482", evidence=ev(0, "abc"))])
    assert score_identifiers(raw, d) == (1.0, 1.0)


def test_score_string_list_both_shapes() -> None:
    raw = {"pressure_tactics": ["fear", {"value": "urgency", "evidence": {}}]}
    d = Dossier(pressure_tactics=[sourced("fear"), sourced("secrecy")])
    assert score_string_list(raw, d, "pressure_tactics") == (0.5, 0.5)


def test_identifier_same_value_different_kind_is_a_miss() -> None:
    raw = {"identifiers": [{"kind": "phone", "value": "12345"}]}
    d = Dossier(
        identifiers=[Identifier(kind="account_number", value="12345", evidence=ev(0, "abc"))]
    )
    assert score_identifiers(raw, d) == (0.0, 0.0)


def id_dossier(kind: IdentifierKind, value: str) -> Dossier:
    return Dossier(identifiers=[Identifier(kind=kind, value=value, evidence=ev(0, "abc"))])


def test_identifier_matching_rules() -> None:
    phone = IdentifierKind.PHONE
    acct = IdentifierKind.ACCOUNT_NUMBER
    raw = {"identifiers": [{"kind": "phone", "value": "07700-900482"}]}
    assert score_identifiers(raw, id_dossier(phone, "07700 900482")) == (1.0, 1.0)
    raw = {"identifiers": [{"kind": "account_number", "value": "99001122"}]}
    got = id_dossier(acct, "sort code 11-22-33, account number 99001122")
    assert score_identifiers(raw, got) == (1.0, 1.0)  # label inside a longer got value
    assert score_identifiers(
        {"identifiers": [{"kind": "account_number", "value": "123"}]}, id_dossier(acct, "1234")
    ) == (0.0, 0.0)
    assert score_identifiers(
        {"identifiers": [{"kind": "account_number", "value": "1234"}]}, id_dossier(acct, "123")
    ) == (0.0, 0.0)


def test_identifier_precision_and_recall_count_matches() -> None:
    raw = {
        "identifiers": [
            {"kind": "phone", "value": "07700900482"},
            {"kind": "alias", "value": "James Carter"},
        ]
    }
    d = Dossier(
        identifiers=[
            Identifier(kind=IdentifierKind.PHONE, value="07700 900482", evidence=ev(0, "abc")),
            Identifier(kind=IdentifierKind.URL, value="http://bad.example", evidence=ev(0, "abc")),
        ]
    )
    assert score_identifiers(raw, d) == (0.5, 0.5)


def test_empty_expected_and_empty_got_is_perfect() -> None:
    assert score_identifiers({"identifiers": []}, Dossier()) == (1.0, 1.0)
    assert score_string_list({"pressure_tactics": []}, Dossier(), "pressure_tactics") == (1.0, 1.0)


def test_empty_expected_with_extra_items_has_zero_precision() -> None:
    d = id_dossier(IdentifierKind.PHONE, "07700900482")
    assert score_identifiers({"identifiers": []}, d) == (0.0, 1.0)
    d2 = Dossier(pressure_tactics=[sourced("fear")])
    assert score_string_list({"pressure_tactics": []}, d2, "pressure_tactics") == (0.0, 1.0)
