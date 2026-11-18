"""Tests for the fake providers."""

from pathlib import Path

import pytest

from natter.providers.fakes import FakeExtractor, FakePersona
from natter.schema import Report

ROOT = Path(__file__).parent.parent
FULL = Report.model_validate_json(
    (ROOT / "docs" / "example_report.json").read_text(encoding="utf-8")
).dossier


def test_persona_returns_lines_in_order_then_cycles() -> None:
    persona = FakePersona(["a", "b"])
    assert [persona.reply([], None) for _ in range(5)] == ["a", "b", "a", "b", "a"]


def test_persona_empty_lines_raise() -> None:
    with pytest.raises(ValueError):
        FakePersona([])


def test_persona_has_default_lines() -> None:
    assert FakePersona().reply([], None) != ""


def test_extractor_returns_preset() -> None:
    assert FakeExtractor(FULL).extract([]) == FULL


def test_extractor_copy_cannot_change_preset() -> None:
    extractor = FakeExtractor(FULL)
    first = extractor.extract([])
    first.identifiers.clear()  # mutate the returned copy
    assert extractor.extract([]) == FULL
