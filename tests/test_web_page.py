"""Tests for the page files and the routes that serve them."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from natter.web.server import create_app
from tests.live_fakes import make_call

PAGE = Path(__file__).parent.parent / "natter" / "web"


@pytest.fixture
def client() -> TestClient:
    app = create_app("live", make_call, None, 15)
    return TestClient(app, base_url="http://127.0.0.1:8000")


def read(name: str) -> str:
    return (PAGE / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("path", "media_type"),
    [("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css")],
)
def test_page_files_are_served_with_their_type_and_csp(
    client: TestClient, path: str, media_type: str
) -> None:
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(media_type)
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_html_loads_the_script_and_style_files_and_nothing_inline() -> None:
    html = read("index.html")
    assert '<script src="/app.js"' in html
    assert '<link rel="stylesheet" href="/style.css"' in html
    assert re.search(r"<script(?![^>]*\bsrc=)", html) is None  # no inline script
    assert re.search(r"<style", html) is None  # no inline style block
    assert re.search(r"\son[a-z]+\s*=", html) is None  # no onclick= style handlers
    assert re.search(r"\sstyle\s*=", html) is None  # no style= attributes


DANGERS = [".innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function("]


@pytest.mark.parametrize("danger", DANGERS)
def test_script_never_turns_text_into_html_or_code(danger: str) -> None:
    assert danger not in read("app.js")


def test_every_element_the_script_looks_up_is_in_the_page() -> None:
    ids = re.findall(r'getElementById\("([^"]+)"\)', read("app.js"))
    assert ids  # the script does look elements up
    html = read("index.html")
    missing = [i for i in ids if f'id="{i}"' not in html]
    assert missing == []


def test_the_owner_fact_row_function_exists() -> None:
    assert "function renderFactRow(fact)" in read("app.js")


def test_query_parameters_cannot_change_a_page_file(client: TestClient) -> None:
    real = client.get("/").text
    r = client.get("/", params={"body": "<script>evil()</script>", "media_type": "text/plain"})
    assert r.text == real
    assert r.headers["content-type"].startswith("text/html")


def test_hidden_controls_really_are_hidden() -> None:
    # A display: rule (like .controls { display: flex }) beats the browser's own
    # [hidden] rule, so the page needs its own, or both control sets always show.
    css = re.sub(r"\s+", " ", read("style.css"))
    assert "[hidden] { display: none !important; }" in css
    # Both control sets start hidden; showMode() in app.js reveals the right one
    html = read("index.html")
    assert re.search(r'id="replay-controls"[^>]*\bhidden\b', html)
    assert re.search(r'id="live-form"[^>]*\bhidden\b', html)


def test_script_treats_replay_finished_as_the_end_of_the_call() -> None:
    # A text check, not a browser test: the 409 "replay finished" answer must end the
    # call on the page (so Next turn is switched off), e.g. after a reload.
    js = read("app.js")
    assert 'answer.data.detail === "replay finished"' in js


def test_script_uses_one_shared_audio_player() -> None:
    # A text check, not a browser test: one shared player, stopped and rewound before
    # each new clip, so two clips never play over each other; a failed play() is caught.
    js = read("app.js")
    assert "let currentAudio = null;" in js
    assert "function playClip(audioUrl)" in js
    assert "currentAudio.pause();" in js
    assert "currentAudio.currentTime = 0;" in js
    assert ".catch(" in js
    assert js.count("new Audio(") == 1  # only playClip makes a player
    assert 'addEventListener("click", () => playClip(audioUrl))' in js


def test_reset_stops_the_current_clip() -> None:
    # A text check: the Reset handler's first step stops and rewinds the shared player
    assert 'resetButton.addEventListener("click", async () => {\n  stopClip();' in read("app.js")
