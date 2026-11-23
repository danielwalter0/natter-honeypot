"""Tests for label validation: a bad label is named, never silently scored."""

from typing import Any

import pytest

from natter.labels import label_problem


def test_good_labels_pass_in_both_shapes() -> None:
    template = {
        "is_scam": True,
        "scam_type": "other",
        "claimed_organisation": "HMRC",
        "payment_method": None,
        "amount": {"amount": 450.5, "currency": "GBP"},
        "injection_attempt": None,
        "identifiers": [{"kind": "phone", "value": "0770"}],
        "pressure_tactics": ["fear"],
        "information_requested": ["pin"],
    }
    assert label_problem(template) is None
    full = {
        "scam_type": {"value": "other", "evidence": {}},
        "amount": {"value": {"amount": 1, "currency": "GBP"}, "evidence": {}},
        "pressure_tactics": [{"value": "fear", "evidence": {}}],
    }
    assert label_problem(full) is None
    assert label_problem({}) is None


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"scam_type": "bank"}, "scam_type"),
        ({"payment_method": "cheque"}, "payment_method"),
        ({"pressure_tactics": ["Fear"]}, "pressure_tactics"),
        ({"pressure_tactics": None}, "pressure_tactics"),
        ({"information_requested": ["ssn"]}, "information_requested"),
        ({"is_scam": "false"}, "is_scam"),
        ({"injection_attempt": "false"}, "injection_attempt"),
        ({"injection_attempt": 0}, "injection_attempt"),
        ({"identifiers": None}, "identifiers"),
        ({"identifiers": [{"kind": "fax", "value": "1"}]}, "identifiers"),
        ({"identifiers": [{"kind": "phone", "value": 5}]}, "identifiers"),
        ({"identifiers": ["phone"]}, "identifiers"),
        ({"amount": {"amount": 0, "currency": "GBP"}}, "amount"),
        ({"amount": {"amount": "5", "currency": "GBP"}}, "amount"),
        ({"amount": {"amount": 5, "currency": "gbp"}}, "amount"),
        ({"amount": 5}, "amount"),
        ({"claimed_organisation": 7}, "claimed_organisation"),
    ],
)
def test_bad_labels_name_the_field(raw: dict[str, Any], field: str) -> None:
    assert label_problem(raw) == field
