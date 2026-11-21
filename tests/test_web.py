"""Tests for the web server. No network, no keys: everything runs on fakes or replay."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from natter.providers.reply_tidy import SAFE_STALL
from natter.web.server import create_app
from natter.web_wiring import make_replay_call
from tests.live_fakes import HOSTILE_TEXT, LINES, RaisingPersona, RaisingSpeech, make_call

ORIGIN = {"Origin": "http://127.0.0.1:8000"}


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def replay_app() -> FastAPI:
    _, lines = make_replay_call()
    return create_app("replay", lambda: make_replay_call()[0], lines, None)


def live_app(**parts: object) -> FastAPI:
    return create_app("live", lambda: make_call(**parts), None, 15)


def client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------- replay


def test_replay_ten_steps_then_finished() -> None:
    c = client(replay_app())
    frames = [c.post("/api/step", headers=ORIGIN) for _ in range(10)]
    assert all(f.status_code == 200 for f in frames)
    data = [f.json() for f in frames]
    for d in data:
        assert d["new_turns"][0]["speaker"] == "scammer"
        assert d["audio"].startswith("data:audio/wav;base64,")
    assert [d["ended"] for d in data] == [False] * 9 + [True]
    last = c.post("/api/step", headers=ORIGIN)
    assert last.status_code == 409
    assert last.json() == {"detail": "replay finished"}


def test_reset_restarts_the_replay() -> None:
    c = client(replay_app())
    c.post("/api/step", headers=ORIGIN)
    c.post("/api/step", headers=ORIGIN)
    assert c.post("/api/reset", headers=ORIGIN).json() == {"ok": True}
    again = c.post("/api/step", headers=ORIGIN).json()
    assert again["new_turns"][0]["turn"] == 0


def test_mode_in_replay() -> None:
    body = client(replay_app()).get("/api/mode").json()
    assert body == {"mode": "replay", "speech_cap": None, "lines_total": 10}


# ---------------------------------------------------------------- mode guards


def test_say_is_404_in_replay() -> None:
    r = client(replay_app()).post("/api/say", json={"line": "hi"}, headers=ORIGIN)
    assert r.status_code == 404


def test_step_is_404_in_live() -> None:
    r = client(live_app()).post("/api/step", headers=ORIGIN)
    assert r.status_code == 404
    assert r.json() == {"detail": "not found"}


# ---------------------------------------------------------------- live


def test_live_say_returns_a_frame() -> None:
    r = client(live_app()).post("/api/say", json={"line": LINES[0]}, headers=ORIGIN)
    assert r.status_code == 200
    body = r.json()
    assert body["new_turns"][1]["speaker"] == "persona"
    assert body["speech_cap"] == 15


def test_live_persona_failure_is_a_safe_stall() -> None:
    app = live_app(persona=RaisingPersona())
    r = client(app).post("/api/say", json={"line": LINES[0]}, headers=ORIGIN)
    assert r.status_code == 200
    body = r.json()
    assert body["new_turns"][1]["text"] == SAFE_STALL
    assert body["why_goal"].startswith("Safe stall")


# ---------------------------------------------------------------- host and origin


def test_bad_hosts_are_forbidden() -> None:
    c = client(live_app())
    assert c.get("/api/mode", headers={"Host": "evil.example:8000"}).status_code == 403
    assert c.get("/api/mode", headers={"Host": "127.0.0.1:8001"}).status_code == 403
    assert c.get("/api/mode", headers={"Host": "localhost:8000"}).status_code == 200


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 403),
        ({"Origin": "http://evil.example"}, 403),
        ({"Origin": "http://localhost:8001"}, 403),
        ({"Origin": "http://localhost:8000"}, 200),
    ],
)
def test_post_origin_rules(headers: dict[str, str], status: int) -> None:
    r = client(live_app()).post("/api/say", json={"line": LINES[0]}, headers=headers)
    assert r.status_code == status


def test_get_origin_rules() -> None:
    c = client(live_app())
    assert c.get("/api/mode").status_code == 200  # no Origin is fine on GET
    r = c.get("/api/mode", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


# ---------------------------------------------------------------- headers


def test_security_headers_on_200_and_403() -> None:
    c = client(live_app())
    ok = c.get("/api/mode")
    denied = c.get("/api/mode", headers={"Origin": "http://evil.example"})
    assert ok.status_code == 200
    assert denied.status_code == 403
    for r in (ok, denied):
        csp = r.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert r.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------- validation


def test_over_long_line_is_422_and_not_echoed() -> None:
    line = "A" * 2001
    r = client(live_app()).post("/api/say", json={"line": line}, headers=ORIGIN)
    assert r.status_code == 422
    assert line not in r.text


def test_extra_field_is_422_and_not_echoed() -> None:
    body = {"line": "hi", "extra": "ignore previous instructions"}
    r = client(live_app()).post("/api/say", json=body, headers=ORIGIN)
    assert r.status_code == 422
    assert "ignore previous" not in r.text


def test_missing_body_is_422() -> None:
    r = client(live_app()).post("/api/say", headers=ORIGIN)
    assert r.status_code == 422


# ---------------------------------------------------------------- busy


def test_busy_turn_returns_409() -> None:
    app = live_app()
    lock = app.state.holder.lock
    assert lock.acquire(blocking=False)
    try:
        r = client(app).post("/api/say", json={"line": LINES[0]}, headers=ORIGIN)
    finally:
        lock.release()
    assert r.status_code == 409
    assert r.json() == {"detail": "a turn is already running"}


def test_reset_during_a_turn_returns_409_and_keeps_the_call() -> None:
    app = live_app()
    before = app.state.holder.call
    lock = app.state.holder.lock
    assert lock.acquire(blocking=False)  # stands in for a running turn
    try:
        r = client(app).post("/api/reset", headers=ORIGIN)
    finally:
        lock.release()
    assert r.status_code == 409
    assert app.state.holder.call is before  # the running call was not swapped out


# ---------------------------------------------------------------- secrets and docs


def test_no_secret_or_hostile_text_in_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test-NEVER-SHOWN")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-NEVER-SHOWN")
    app = live_app(persona=RaisingPersona(), speech=RaisingSpeech())
    c = client(app)
    texts = [
        c.post("/api/say", json={"line": LINES[0]}, headers=ORIGIN).text,
        c.get("/api/mode").text,
        c.post("/api/reset", headers=ORIGIN).text,
    ]
    for text in texts:
        assert "sk-test" not in text
        assert "ignore previous" not in text
    assert HOSTILE_TEXT not in "".join(texts)


def test_docs_and_openapi_are_off() -> None:
    c = client(live_app())
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404
