"""Tests for `python -m natter.web`. No server is started: main() gets a fake runner."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from natter.live import LiveCall
from natter.web import __main__ as web_main
from tests.live_fakes import make_call


class FakeRun:
    """Stands in for uvicorn.run and remembers what it was given."""

    def __init__(self) -> None:
        self.calls: list[tuple[FastAPI, str, int]] = []

    def __call__(self, app: FastAPI, host: str, port: int, server_header: bool) -> None:
        self.calls.append((app, host, port))


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def mode_of(app: FastAPI) -> dict[str, object]:
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    data: dict[str, object] = client.get("/api/mode").json()
    return data


def test_replay_needs_no_keys_and_binds_to_localhost() -> None:
    run = FakeRun()
    web_main.main(["--replay"], run=run)
    [(app, host, port)] = run.calls
    assert host == "127.0.0.1"  # never 0.0.0.0
    assert port == 8000
    assert mode_of(app) == {"mode": "replay", "speech_cap": None, "lines_total": 10}


def test_no_flag_means_replay() -> None:
    run = FakeRun()
    web_main.main([], run=run)
    assert mode_of(run.calls[0][0])["mode"] == "replay"


def test_live_without_keys_exits_1_and_names_the_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = FakeRun()
    with pytest.raises(SystemExit) as stop:
        web_main.main(["--live"], run=run)
    assert stop.value.code == 1
    assert "_API_KEY is not set" in capsys.readouterr().out
    assert run.calls == []  # no server started


def test_live_prints_the_spend_cap_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_live_call() -> LiveCall:
        return make_call()

    monkeypatch.setattr(web_main, "make_live_call", fake_live_call)
    run = FakeRun()
    web_main.main(["--live"], run=run)
    assert "No daily spend cap" in capsys.readouterr().out
    assert mode_of(run.calls[0][0]) == {"mode": "live", "speech_cap": 15, "lines_total": None}


def test_replay_and_live_together_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as stop:
        web_main.main(["--replay", "--live"], run=FakeRun())
    assert stop.value.code == 2
