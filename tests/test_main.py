"""Tests for the command-line glue."""

import re
from datetime import UTC, datetime
from pathlib import Path

from natter.__main__ import make_call_id, save_report
from natter.schema import Dossier, Report, Turn

PATTERN = r"^[a-z0-9_-]{1,64}$"


def test_call_id_matches_schema_pattern() -> None:
    """The generated call id is lowercase and fits the schema pattern."""
    call_id = make_call_id("bank-fraud-01", datetime(2026, 11, 18, 9, 30, 0, tzinfo=UTC))
    assert call_id == "bank-fraud-01-20261118t093000z"
    assert re.match(PATTERN, call_id)


def test_save_report_round_trips(tmp_path: Path) -> None:
    """A saved report loads back through the schema unchanged."""
    report = Report(
        call_id="demo-20261118t093000z",
        scenario_id="demo",
        mode="replay",
        turns=[Turn(index=0, speaker="scammer", text="hello")],
        dossier=Dossier(),
        provenance={"persona": "fake-persona"},
    )
    path = save_report(report, tmp_path)
    assert path == tmp_path / "demo-20261118t093000z.json"
    loaded = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded == report
