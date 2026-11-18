"""Contract tests: the committed docs match the schema, and the schema stays strict."""

import json
from pathlib import Path

import pydantic
import pytest

from natter.schema import Report, Sourced

# Build paths from this file, so tests work from any current directory
ROOT = Path(__file__).parent.parent


def test_json_schema_file_matches_model() -> None:
    committed = json.loads((ROOT / "docs" / "report.schema.json").read_text(encoding="utf-8"))
    assert Report.model_json_schema() == committed


def test_example_report_is_valid() -> None:
    text = (ROOT / "docs" / "example_report.json").read_text(encoding="utf-8")
    Report.model_validate_json(text)


def test_sourced_rejects_extra_key() -> None:
    payload = {
        "value": "hello",
        "evidence": {"turn": 0, "quote": "hello there", "confidence": 0.5},
    }
    Sourced[str].model_validate(payload)  # the valid payload passes
    with pytest.raises(pydantic.ValidationError):
        Sourced[str].model_validate({**payload, "unknown": 1})
