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


# --- voice input in live mode (text checks, not browser tests) ---


def test_voice_uses_the_browser_recogniser_in_british_english() -> None:
    js = read("app.js")
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in js
    assert 'recogniser.lang = "en-GB";' in js
    assert "recogniser.interimResults = true;" in js  # interim text is shown as it is heard


def test_heard_and_typed_lines_share_the_one_say_path() -> None:
    # Only sendLine calls /api/say, so a heard line gets every guard a typed line gets
    js = read("app.js")
    assert js.count('runTurn("/api/say"') == 1
    # Listening pauses before the turn starts (the turn then runs while filler plays)
    assert 'pauseListening();\n  const turn = runTurn("/api/say", { line: line });' in js
    assert 'if (line !== "") sendLine(line);' in js  # a final result from the recogniser
    assert "if (await sendLine(line)) lineInput.value" in js  # the typed fallback


def test_listening_waits_for_the_reply_audio_to_finish() -> None:
    js = read("app.js")
    assert "if (await playClip(latestAudio)) await clipStopped();" in js
    assert 'currentAudio.addEventListener("pause", resolve, { once: true });' in js
    assert "return currentAudio.play().then(() => true).catch(" in js  # says if it started


def test_recogniser_errors_stop_the_call_and_reset_stops_it_too() -> None:
    js = read("app.js")
    assert "recogniser.onerror = (event) => {" in js
    assert 'event.error === "no-speech" || event.error === "aborted"' in js
    # Reset's first two steps: stop the clip, then stop listening (comments allowed after each)
    reset = (
        r'resetButton\.addEventListener\("click", async \(\) => \{\n'
        r"  stopClip\(\);.*\n  stopCall\(\);"
    )
    assert re.search(reset, js)


def test_voice_controls_and_unsupported_line_are_in_the_page() -> None:
    html = read("index.html")
    assert re.search(r'id="stop-call-button"[^>]*\bhidden\b', html)  # shown once a call starts
    assert re.search(r'id="listening"[^>]*\bhidden\b', html)
    assert re.search(r'id="voice-unsupported"[^>]*\bhidden\b', html)
    assert "Voice input needs Chrome or Edge." in html
    js = read("app.js")
    assert "if (!Recogniser) {" in js  # no recogniser: hide the buttons, show the line


# --- latency filler in live mode (text checks, not browser tests) ---


def function_body(js: str, name: str) -> str:
    """The text of one top-level function in app.js, from its name to its closing brace."""
    match = re.search(
        rf"\nasync function {name}\(.*?\n\}}\n|\nfunction {name}\(.*?\n\}}\n", js, re.S
    )
    assert match, name
    return match.group(0)


def test_filler_clips_come_from_the_mode_answer() -> None:
    js = read("app.js")
    assert "let fillerClips = [];" in js  # none until the server sends some
    assert "fillerClips = Array.isArray(info.filler) ? info.filler : [];" in js


def test_filler_starts_with_the_turn_and_the_reply_waits_for_it() -> None:
    js = read("app.js")
    send = function_body(js, "sendLine")
    assert "const fillers = playFillers(turn);" in send  # started before the turn is awaited
    assert send.index("playFillers(turn)") < send.index("await turn")
    after = function_body(js, "playReplyThenListen")
    assert after.index("await fillers;") < after.index("playClip(latestAudio)")


def test_at_most_two_fillers_and_none_without_clips() -> None:
    body = function_body(read("app.js"), "playFillers")
    assert "for (let played = 0; played < 2; played++) {" in body
    assert "if (fillerClips.length === 0 || (played > 0 && replyReady)) return;" in body
    assert "await clipStopped();" in body  # listening stays paused until each clip ends


def test_filler_is_never_the_same_as_the_last_one() -> None:
    body = function_body(read("app.js"), "pickFiller")
    assert "Math.random()" in body
    assert "if (fillerClips.length > 1 && i === lastFiller) {" in body


def test_filler_never_appears_on_the_page_as_a_reply() -> None:
    js = read("app.js")
    for name in ("playFillers", "pickFiller"):
        body = function_body(js, name)
        assert "addBubble" not in body and "textContent" not in body


def test_reply_autoplays_after_typed_lines_but_only_a_call_listens() -> None:
    js = read("app.js")
    after = function_body(js, "playReplyThenListen")
    # The reply plays whether the line was typed or heard (no voice call needed)
    assert "if (ok && latestAudio) {" in after
    assert "callActive" not in after
    # Listening only ever starts during a voice call, so a typed line never starts it
    assert "if (!callActive || paused || ended) return;" in function_body(js, "startListening")
