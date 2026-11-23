"""Tests for the evaluation table and the per-scenario scoring run (replay, no keys)."""

from pathlib import Path

from natter.__main__ import ROOT
from natter.eval_table import COLUMNS, render_table
from natter.evaluate import evaluate_all, evaluate_scenario, valid_scenario_name, verdict


def test_render_table_header_rows_and_blanks() -> None:
    text = render_table([{"scenario": "a-01", "status": "ok"}, {"scenario": "b-01"}])
    lines = text.splitlines()
    assert lines[0].startswith("| scenario | status |")
    assert lines[1].startswith("|---")
    assert lines[2].startswith("| a-01 | ok |")
    assert lines[3].startswith("| b-01 |  |")  # missing cells are blank
    assert all(line.count("|") == len(COLUMNS) + 1 for line in lines)


def test_valid_scenario_name() -> None:
    assert valid_scenario_name("bank-fraud-02")
    assert not valid_scenario_name("../etc")
    assert not valid_scenario_name("")
    assert not valid_scenario_name("A" * 3)
    assert not valid_scenario_name("a" * 65)


def test_recorded_scenario_is_scored() -> None:
    row = evaluate_scenario(ROOT / "scenarios" / "bank-fraud-01")
    assert row["status"] == "scored"
    verified, total = row["quotes verified"].split("/")
    assert verified == total and int(total) > 0  # every quote checks out


def test_template_scenarios_are_not_scored(tmp_path: Path) -> None:
    folder = tmp_path / "x-01"
    folder.mkdir()
    (folder / "expected.json").write_text('{"_status": "template"}', encoding="utf-8")
    row = evaluate_scenario(folder)
    assert row["status"] == "template, not labelled"
    assert "is_scam" not in row


def make_folder(root: Path, name: str, expected: str, script: bool = False) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "expected.json").write_text(expected, encoding="utf-8")
    if script:
        (folder / "script.json").write_text(
            '{"scenario_id": "y-01", "scammer_turns": [{"text": "hello there"}]}',
            encoding="utf-8",
        )
    return folder


def test_unrecorded_scenario_reports_not_recorded(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "y-01", "{}", script=True)
    assert evaluate_scenario(folder)["status"] == "not recorded"
    assert not (folder / "cache").exists()  # replay must not create a cache folder


def test_bad_label_gives_a_named_status_and_no_scores(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "z-01", '{"scam_type": "bank"}', script=True)
    row = evaluate_scenario(folder)
    assert row["status"] == "bad label: scam_type"
    assert "is_scam" not in row


def test_evaluate_all_covers_every_scenario_with_labels(tmp_path: Path) -> None:
    make_folder(tmp_path, "c-template", '{"_status": "template"}')
    make_folder(tmp_path, "b-unrecorded", "{}", script=True)
    make_folder(tmp_path, "a-bad", '{"is_scam": "false"}')
    (tmp_path / "no-labels").mkdir()  # no expected.json: skipped
    rows = evaluate_all(tmp_path)
    assert [(r["scenario"], r["status"]) for r in rows] == [
        ("a-bad", "bad label: is_scam"),
        ("b-unrecorded", "not recorded"),
        ("c-template", "template, not labelled"),
    ]


def test_verdict_cells() -> None:
    assert (verdict(True), verdict(False), verdict(None)) == ("ok", "miss", "-")
