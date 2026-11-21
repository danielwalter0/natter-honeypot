import pytest

from natter.__main__ import CACHE, MAX_TURNS, SCENARIO, load_lines, replay_providers
from natter.audio_cache import is_wav
from natter.live import LiveReply
from natter.providers.reply_tidy import SAFE_STALL
from natter.session import run_session
from natter.web_wiring import make_replay_call


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Replay must work with no keys at all
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def play_all() -> tuple[object, list[LiveReply]]:
    call, lines = make_replay_call()
    return call, [call.say(line) for line in lines]


def test_live_replay_matches_run_session() -> None:
    call, lines = make_replay_call()
    for line in lines:
        call.say(line)
    result = run_session(load_lines(SCENARIO), *replay_providers(CACHE), MAX_TURNS)
    live = [(t.index, t.speaker, t.text) for t in call.state.transcript]
    plain = [(t.index, t.speaker, t.text) for t in result.transcript]
    assert live == plain
    assert call.state.dossier == result.dossier
    assert call.state.goals == result.goals


def test_every_reply_has_text_and_wav_and_no_problems() -> None:
    _, replies = play_all()
    assert replies
    for reply in replies:
        assert reply.text
        assert reply.audio is not None and is_wav(reply.audio)
        assert reply.notes == []
        assert reply.rejections == []


def test_no_reply_is_the_safe_stall() -> None:
    _, replies = play_all()
    assert all(reply.text != SAFE_STALL for reply in replies)
