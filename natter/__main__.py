"""Entry point for `python -m natter`: replays the default scenario and saves a report."""

import json
from datetime import UTC, datetime
from pathlib import Path

from natter.providers.fakes import FakeExtractor, FakePersona
from natter.schema import Dossier, Report
from natter.session import run_session

ROOT = Path(__file__).parent.parent  # the project folder, not the current directory
SCENARIO = ROOT / "scenarios" / "bank-fraud-01"
REPORTS = ROOT / "reports"
MAX_TURNS = 40


def load_lines(folder: Path) -> list[str]:
    """Read script.json and return the scammer's lines in order."""
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    return [item["text"] for item in script["scammer_turns"]]


def make_call_id(scenario_id: str, now: datetime) -> str:
    """Build an id like bank-fraud-01-20261118t093000z (matches the schema pattern)."""
    return f"{scenario_id}-{now.strftime('%Y%m%dt%H%M%Sz')}"


def build_report(folder: Path) -> tuple[Report, int]:
    """Run the scenario in replay mode. Return the report and the rejection count."""
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    scenario_id: str = script["scenario_id"]
    expected = Dossier.model_validate_json((folder / "expected.json").read_text(encoding="utf-8"))
    persona = FakePersona()
    extractor = FakeExtractor(expected)
    result = run_session(load_lines(folder), persona, extractor, MAX_TURNS)
    report = Report(
        call_id=make_call_id(scenario_id, datetime.now(UTC)),
        scenario_id=scenario_id,
        mode="replay",
        turns=result.transcript,
        dossier=result.dossier,
        provenance={"persona": persona.name, "extractor": extractor.name},
    )
    return report, len(result.rejections)


def save_report(report: Report, folder: Path = REPORTS) -> Path:
    """Write the report as <call_id>.json inside folder and return the path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{report.call_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def main() -> None:
    report, rejection_count = build_report(SCENARIO)
    for turn in report.turns:
        print(f"[{turn.index}] {turn.speaker}: {turn.text}")
    print(report.dossier.model_dump_json(indent=2))
    print(f"Rejections: {rejection_count}")
    print(f"Saved: {save_report(report)}")


if __name__ == "__main__":
    main()
