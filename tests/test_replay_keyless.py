import json
from pathlib import Path

import pytest

from natter.__main__ import MAX_TURNS, SCENARIO, load_lines
from natter.cache import Cache, CachedExtractor, CachedPersona
from natter.picker import Goal
from natter.providers import claude_extractor, groq_persona
from natter.providers.claude_extractor import ClaudeExtractor
from natter.providers.groq_persona import GroqPersona
from natter.providers.replay_only import ReplayOnly
from natter.schema import Dossier
from natter.session import run_session
from tests.fake_clients import FakeFactory, claude_response


def dossier_reply() -> object:
    """One fact the check accepts (quote is in scammer turn 0) and one it rejects."""
    good = {"turn": 0, "quote": "Kestrel Bank", "confidence": 0.9}
    bad = {"turn": 0, "quote": "this was never said", "confidence": 0.9}
    raw = {
        "claimed_organisation": {"value": "Kestrel Bank", "evidence": good},
        "scam_type": {"value": "bank_impersonation", "evidence": bad},
    }
    return claude_response(json.dumps(raw))


def test_replay_only_raises_when_called() -> None:
    provider = ReplayOnly("x")
    with pytest.raises(RuntimeError, match="replay-only provider was called"):
        provider.reply([], Goal.AMOUNT)
    with pytest.raises(RuntimeError, match="replay-only provider was called"):
        provider.extract([])


def test_recorded_cache_replays_without_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Test-local stand-ins so this test does not depend on the owner's builders
    monkeypatch.setattr(claude_extractor, "build_user_message", lambda t: "stub")
    monkeypatch.setattr(groq_persona, "build_messages", lambda t, g: [{"role": "system"}])
    monkeypatch.setattr(groq_persona, "introduces_new_number", lambda r, t: False)
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    record = Cache(tmp_path, "record")
    persona = CachedPersona(GroqPersona(client_factory=FakeFactory("groq")), record)
    extractor = CachedExtractor(
        ClaudeExtractor(client_factory=FakeFactory("claude", dossier_reply())), record
    )
    lines = load_lines(SCENARIO)
    recorded = run_session(lines, persona, extractor, MAX_TURNS)

    # Now the keys are gone and only the cache can answer
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    replay = Cache(tmp_path, "replay")
    persona2 = CachedPersona(ReplayOnly(f"groq:{groq_persona.DEFAULT_MODEL}"), replay)
    extractor2 = CachedExtractor(ReplayOnly(f"claude:{claude_extractor.DEFAULT_MODEL}"), replay)
    replayed = run_session(lines, persona2, extractor2, MAX_TURNS)
    assert replayed.transcript == recorded.transcript
    # The comparisons below must mean something, so the dossier is not empty
    assert recorded.dossier != Dossier() and recorded.rejections
    assert replayed.dossier == recorded.dossier
    assert replayed.rejections == recorded.rejections
