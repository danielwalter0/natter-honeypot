"""Replay each labelled scenario from its cassettes and score it against its labels."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natter.__main__ import MAX_TURNS, load_lines, replay_providers
from natter.cache import CacheMiss
from natter.labels import label_problem
from natter.list_scoring import score_identifiers, score_string_list
from natter.scoring import (
    digit_leaks,
    first_capture,
    is_template,
    match_amount,
    match_is_scam,
    match_org,
    match_scalar,
    quote_check,
    safe_stalls,
)
from natter.session import SessionResult, run_session

NAME_PATTERN = re.compile(r"[a-z0-9_-]{1,64}")


def valid_scenario_name(name: str) -> bool:
    """Same shape as a report id: keeps a name from reaching outside scenarios/."""
    return NAME_PATTERN.fullmatch(name) is not None


def verdict(ok: bool | None) -> str:
    """ok or miss; "-" when the label says not scored."""
    if ok is None:
        return "-"
    return "ok" if ok else "miss"


def pair(scores: tuple[float, float]) -> str:
    """Precision/recall as "0.75/1.00"."""
    return f"{scores[0]:.2f}/{scores[1]:.2f}"


def turn_text(turn: int | None) -> str:
    return "-" if turn is None else str(turn)


@dataclass
class Outcome:
    """One scenario after replay: its labels and (if scored) the session result."""

    name: str
    status: str  # "scored", "template, not labelled", "bad label: x" or "not recorded"
    raw: dict[str, Any]
    result: SessionResult | None


def replay_session(folder: Path) -> SessionResult:
    """Replay the cassettes for one scenario. Raises CacheMiss if not recorded. No keys."""
    persona, extractor = replay_providers(folder / "cache")
    return run_session(load_lines(folder), persona, extractor, MAX_TURNS)


def replay_scenario(folder: Path) -> Outcome:
    """Read the labels and replay once. Template and bad-label scenarios are not replayed."""
    raw: dict[str, Any] = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    if is_template(raw):
        return Outcome(folder.name, "template, not labelled", raw, None)
    problem = label_problem(raw)
    if problem is not None:
        return Outcome(folder.name, f"bad label: {problem}", raw, None)
    try:
        return Outcome(folder.name, "scored", raw, replay_session(folder))
    except CacheMiss:
        return Outcome(folder.name, "not recorded", raw, None)


def row_for(outcome: Outcome) -> dict[str, str]:
    """Build the table row. Only a scored outcome has scores."""
    row = {"scenario": outcome.name, "status": outcome.status}
    result, raw = outcome.result, outcome.raw
    if result is None:
        return row
    dossier, transcript = result.dossier, result.transcript
    verified, total = quote_check(dossier, transcript)
    callback, payment = first_capture(dossier)
    row.update(
        {
            "is_scam": verdict(match_is_scam(raw, dossier)),
            "scam_type": verdict(match_scalar(raw, dossier, "scam_type")),
            "org": verdict(match_org(raw, dossier)),
            "payment": verdict(match_scalar(raw, dossier, "payment_method")),
            "amount": verdict(match_amount(raw, dossier)),
            "injection": verdict(match_scalar(raw, dossier, "injection_attempt")),
            "identifiers P/R": pair(score_identifiers(raw, dossier)),
            "tactics P/R": pair(score_string_list(raw, dossier, "pressure_tactics")),
            "info P/R": pair(score_string_list(raw, dossier, "information_requested")),
            "rejections": str(len(result.rejections)),
            "quotes verified": f"{verified}/{total}",
            "digit leaks": str(digit_leaks(transcript)),
            "safe stalls": str(safe_stalls(transcript)),
            "callback turn": turn_text(callback),
            "payment turn": turn_text(payment),
        }
    )
    return row


def evaluate_scenario(folder: Path) -> dict[str, str]:
    """Replay one scenario and return its table row."""
    return row_for(replay_scenario(folder))


def replay_all(scenarios: Path) -> list[Outcome]:
    """One outcome per scenario folder that has an expected.json, sorted by name."""
    folders = sorted(p for p in scenarios.iterdir() if (p / "expected.json").is_file())
    return [replay_scenario(folder) for folder in folders]


def evaluate_all(scenarios: Path) -> list[dict[str, str]]:
    """The table rows for every scenario."""
    return [row_for(outcome) for outcome in replay_all(scenarios)]
