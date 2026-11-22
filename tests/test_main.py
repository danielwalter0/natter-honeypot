"""Tests for the command-line glue."""

import io
import json
import re
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import natter.__main__ as natter_main
from natter.__main__ import (
    MAX_TURNS,
    SCENARIO,
    build_report,
    goal_line,
    load_lines,
    main,
    make_call_id,
    save_report,
)
from natter.cache import Cache, CachedExtractor, CachedPersona, CacheMiss
from natter.picker import Goal
from natter.providers import claude_extractor
from natter.schema import Dossier, Evidence, Report, ScamType, Sourced, Turn
from natter.session import run_session

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


# --- python -m natter --replay ---


class SpyPersona:
    """Stands in for the recorded Groq persona: same name, fixed reply, counts calls."""

    name = f"groq:{natter_main.RECORDED_PERSONA_MODEL}"  # the name replay looks up

    def __init__(self) -> None:
        self.calls = 0

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        self.calls += 1
        return "Oh dear, let me find my glasses."


class SpyExtractor:
    """Stands in for the recorded Claude extractor: one fact kept, one rejected."""

    name = f"claude:{claude_extractor.DEFAULT_MODEL}"

    def extract(self, transcript: list[Turn]) -> Dossier:
        good = Evidence(turn=0, quote="Kestrel Bank", confidence=0.9)
        bad = Evidence(turn=0, quote="this was never said", confidence=0.9)
        return Dossier(
            claimed_organisation=Sourced[str](value="Kestrel Bank", evidence=good),
            scam_type=Sourced[ScamType](value=ScamType.BANK_IMPERSONATION, evidence=bad),
        )


def fill_cache(folder: Path) -> SpyPersona:
    """Record one run of the scenario into folder, as record_cassettes.py would."""
    record = Cache(folder, "record")
    spy = SpyPersona()
    persona, extractor = CachedPersona(spy, record), CachedExtractor(SpyExtractor(), record)
    run_session(load_lines(SCENARIO), persona, extractor, MAX_TURNS)
    return spy


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No keys, no sockets, cache and reports in tmp_path. Returns the cache folder."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    cache = tmp_path / "cache"
    fill_cache(cache)
    monkeypatch.setattr(natter_main, "CACHE", cache)
    monkeypatch.setattr(natter_main, "REPORTS", tmp_path / "reports")
    return cache


def test_replay_flag_plays_the_cache_without_keys(
    offline: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--replay"])
    out = capsys.readouterr().out
    assert "[1] persona: Oh dear, let me find my glasses." in out
    assert '"Kestrel Bank"' in out  # the kept fact is in the printed dossier
    # Every rejection is printed with its scammer turn, not just a count
    assert "turn 0, scam_type: quote not found in cited turn" in out
    saved = next((offline.parent / "reports").glob("*.json"))
    report = Report.model_validate_json(saved.read_text(encoding="utf-8"))
    assert report.mode == "replay"
    assert report.provenance == {"persona": SpyPersona.name, "extractor": SpyExtractor.name}


def test_replay_never_calls_a_provider(offline: Path) -> None:
    report, result = build_report(SCENARIO, replay=True)
    assert result.rejections and len(result.rejection_turns) == len(result.rejections)
    assert report.turns[1].text == "Oh dear, let me find my glasses."


def test_replay_with_an_empty_cache_fails_loudly(
    offline: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(natter_main, "CACHE", tmp_path / "empty")
    with pytest.raises(CacheMiss):
        main(["--replay"])


def test_no_flag_still_uses_the_fakes(offline: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    out = capsys.readouterr().out
    assert "[1] persona: Oh hello dear, hold on, let me find my glasses." in out
    assert "Rejections: " in out
    assert not re.search(r"^turn \d+, ", out, re.MULTILINE)  # per-drop lines are --replay only


def test_unknown_flag_errors() -> None:
    with pytest.raises(SystemExit) as info:
        main(["--live"])
    assert info.value.code == 2  # argparse's usage-error exit code


def test_replay_prints_the_goal_trace(offline: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["--replay"])
    out = capsys.readouterr().out
    assert out.index("Rejections:") < out.index("Goal trace") < out.index("Saved:")
    trace = out[out.index("Goal trace") : out.index("Saved:")].splitlines()[1:]
    # SpyExtractor never finds a phone number, so next_goal is callback_number every
    # turn. The session never gives the same goal twice running, so it is passed on
    # every other reply and the replies between get None (a stall).
    expected = [
        f"turn {t}: {'callback_number' if n % 2 == 0 else 'none'}"
        for n, t in enumerate(range(1, 20, 2))
    ]
    assert trace == expected  # callback_number on 1, 5, 9, 13, 17; none on 3, 7, 11, 15, 19


def test_goal_line_names_none_for_no_goal() -> None:
    assert goal_line(3, None) == "turn 3: none"
    assert goal_line(1, Goal.AMOUNT) == "turn 1: amount"


class BrokenStdout:
    """A console that cannot encode anything, like a cp1252 pipe meeting U+2011."""

    def write(self, text: str) -> int:
        raise UnicodeEncodeError("charmap", text, 0, 1, "character maps to <undefined>")

    def flush(self) -> None:
        pass


def test_report_is_saved_even_if_printing_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(natter_main, "REPORTS", tmp_path)
    monkeypatch.setattr(sys, "stdout", BrokenStdout())  # has no reconfigure(): skipped
    with pytest.raises(UnicodeEncodeError):
        main([])
    saved = list(tmp_path.glob("*.json"))
    assert len(saved) == 1
    Report.model_validate_json(saved[0].read_text(encoding="utf-8"))  # a whole report


def test_main_switches_stdout_to_utf8_when_it_can(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, str]] = []

    class Console(io.StringIO):
        def reconfigure(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(natter_main, "REPORTS", tmp_path)
    monkeypatch.setattr(sys, "stdout", Console())
    main([])
    assert calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_replay_names_the_model_the_cassettes_were_recorded_with() -> None:
    # The live default can change; replay must still find the committed cassettes
    names = {
        json.loads(f.read_text(encoding="utf-8"))["provider"]
        for f in natter_main.CACHE.glob("*.json")
    }
    assert f"groq:{natter_main.RECORDED_PERSONA_MODEL}" in names
