"""The terminal loop, with fake providers and scripted input. No network."""

import builtins
import json
import re
from pathlib import Path

import pytest

from natter import live_cli
from natter.live_wiring import build_live_call
from natter.providers.errors import MissingKeyError
from natter.providers.fakes import FakeExtractor, FakePersona, FakeSpeech
from natter.schema import Dossier
from tests.live_fakes import PHONE


def run_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    typed: list[str],
    persona: FakePersona | None = None,
) -> None:
    """Run main() with `typed` as the input lines, then EOF."""
    persona = persona or FakePersona(lines=["Oh hello dear."])
    call = build_live_call(
        persona,
        FakeExtractor(Dossier(identifiers=[PHONE])),
        FakeSpeech(),
        tmp_path,
        throttle_gap_s=0,
    )
    monkeypatch.setattr(live_cli, "make_live_call", lambda: call)
    lines = iter(typed)

    def fake_input(prompt: str = "") -> str:
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)
    live_cli.main()


def test_prints_reply_audio_requests_and_dossier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_cli(monkeypatch, tmp_path, ["Call me on 07700 900482 now."])
    out = capsys.readouterr().out
    assert "natter: Oh hello dear." in out
    assert re.search(r"audio: \d+ bytes", out)
    assert "speech requests used: 1" in out
    dossier_line = [x for x in out.splitlines() if x.startswith("{")][-1]
    assert json.loads(dossier_line)["identifiers"][0]["value"] == "07700 900482"


def test_quit_stops_before_the_next_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = FakePersona(lines=["Oh hello dear."])
    run_cli(monkeypatch, tmp_path, ["hello", "quit", "never reached"], persona)
    assert persona.position == 1
    assert "never reached" not in capsys.readouterr().out


def test_stops_when_the_call_ends(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    persona = FakePersona(lines=["Oh hello dear."])
    call = build_live_call(
        persona, FakeExtractor(Dossier()), FakeSpeech(), tmp_path, throttle_gap_s=0
    )
    call.max_turns = 2  # the second turn is her reply, so the call ends after one say()
    monkeypatch.setattr(live_cli, "make_live_call", lambda: call)
    inputs = iter(["one", "two"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(inputs))
    live_cli.main()
    assert persona.position == 1  # the second line was never read


def test_missing_key_exits_with_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_key() -> None:
        raise MissingKeyError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(live_cli, "make_live_call", no_key)
    with pytest.raises(SystemExit) as info:
        live_cli.main()
    assert info.value.code == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out
