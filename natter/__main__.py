"""Entry point for `python -m natter`: plays the default scenario and saves a report.

No flag: fake providers. --replay: the recorded Groq and Claude answers from the
cache, with no keys and no network.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from natter.cache import Cache, CachedExtractor, CachedPersona
from natter.picker import Goal
from natter.providers import claude_extractor, groq_persona
from natter.providers.base import Extractor, Persona
from natter.providers.fakes import FakeExtractor, FakePersona
from natter.providers.replay_only import ReplayOnly
from natter.schema import Dossier, Report
from natter.session import SessionResult, run_session

ROOT = Path(__file__).parent.parent  # the project folder, not the current directory
SCENARIO = ROOT / "scenarios" / "bank-fraud-01"
CACHE = SCENARIO / "cache"  # written by scripts/record_cassettes.py
REPORTS = ROOT / "reports"
MAX_TURNS = 40


def load_lines(folder: Path) -> list[str]:
    """Read script.json and return the scammer's lines in order."""
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    return [item["text"] for item in script["scammer_turns"]]


def make_call_id(scenario_id: str, now: datetime) -> str:
    """Build an id like bank-fraud-01-20261118t093000z (matches the schema pattern)."""
    return f"{scenario_id}-{now.strftime('%Y%m%dt%H%M%Sz')}"


def fake_providers(folder: Path) -> tuple[Persona, Extractor]:
    """The default: scripted lines, and the scenario's expected dossier."""
    expected = Dossier.model_validate_json((folder / "expected.json").read_text(encoding="utf-8"))
    return FakePersona(), FakeExtractor(expected)


def replay_providers(cache_dir: Path) -> tuple[Persona, Extractor]:
    """Recorded answers only. ReplayOnly raises if the cache ever misses and asks it."""
    cache = Cache(cache_dir, "replay")
    # The names must match the ones used when recording, or every lookup misses
    persona = ReplayOnly(f"groq:{groq_persona.DEFAULT_MODEL}")
    extractor = ReplayOnly(f"claude:{claude_extractor.DEFAULT_MODEL}")
    return CachedPersona(persona, cache), CachedExtractor(extractor, cache)


def build_report(folder: Path, replay: bool = False) -> tuple[Report, SessionResult]:
    """Run the scenario. Return the report and the full session result."""
    script = json.loads((folder / "script.json").read_text(encoding="utf-8"))
    scenario_id: str = script["scenario_id"]
    # CACHE is read here, not as a default argument, so tests can point it elsewhere
    persona, extractor = replay_providers(CACHE) if replay else fake_providers(folder)
    result = run_session(load_lines(folder), persona, extractor, MAX_TURNS)
    report = Report(
        call_id=make_call_id(scenario_id, datetime.now(UTC)),
        scenario_id=scenario_id,
        mode="replay",
        turns=result.transcript,
        dossier=result.dossier,
        provenance={"persona": persona.name, "extractor": extractor.name},
    )
    return report, result


def save_report(report: Report, folder: Path = REPORTS) -> Path:
    """Write the report as <call_id>.json inside folder and return the path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{report.call_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def goal_line(turn_index: int, goal: Goal | None) -> str:
    """One line of the goal trace, e.g. "turn 1: callback_number" or "turn 3: none"."""
    return f"turn {turn_index}: {'none' if goal is None else goal.value}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read the command line. An unknown flag prints usage and exits with code 2."""
    parser = argparse.ArgumentParser(prog="python -m natter")
    parser.add_argument(
        "--replay", action="store_true", help="play the recorded Groq and Claude answers"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """argv=None reads sys.argv; tests pass a list instead."""
    args = parse_args(argv)
    report, result = build_report(SCENARIO, replay=args.replay)
    for turn in report.turns:
        print(f"[{turn.index}] {turn.speaker}: {turn.text}")
    print(report.dossier.model_dump_json(indent=2))
    print(f"Rejections: {len(result.rejections)}")
    if args.replay:
        # Each drop with the scammer turn whose extraction proposed it
        for turn_index, rejection in zip(result.rejection_turns, result.rejections, strict=True):
            print(f"turn {turn_index}, {rejection.field}: {rejection.reason}")
    # Which goal steered each persona reply (goals has one entry per persona turn)
    print("Goal trace")
    persona_turns = [turn.index for turn in result.transcript if turn.speaker == "persona"]
    for turn_index, goal in zip(persona_turns, result.goals, strict=True):
        print(goal_line(turn_index, goal))
    print(f"Saved: {save_report(report, REPORTS)}")


if __name__ == "__main__":
    main()
