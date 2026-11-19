import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import groq
import httpx
import httpx2
import pytest

from natter.cache import Cache, CachedExtractor, CachedPersona
from natter.providers import claude_extractor, groq_persona
from natter.providers.claude_extractor import ClaudeExtractor
from natter.providers.groq_persona import GroqPersona
from natter.schema import Turn
from tests.fake_clients import FakeFactory

SENTINEL = "sk-SENTINEL-do-not-leak"
TRANSCRIPT = [Turn(index=0, speaker="scammer", text="hello")]


@pytest.fixture(autouse=True)
def stub_builders(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test-local stand-ins so these tests do not depend on the owner's builders
    monkeypatch.setattr(claude_extractor, "build_user_message", lambda t: "stub")
    monkeypatch.setattr(groq_persona, "build_messages", lambda t, g: [{"role": "system"}])


def assert_no_leak(provider: object, folder: Path) -> None:
    assert SENTINEL not in repr(provider)
    assert SENTINEL not in repr(vars(provider))
    for path in folder.iterdir():
        assert SENTINEL.encode() not in path.read_bytes()


def test_groq_key_is_used_but_never_stored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL)
    factory = FakeFactory("groq")
    provider = GroqPersona(client_factory=factory)
    CachedPersona(provider, Cache(tmp_path, "record")).reply(TRANSCRIPT, None)
    assert factory.factory_kwargs["api_key"] == SENTINEL  # the SDK did get the key
    assert_no_leak(provider, tmp_path)


def test_claude_key_is_used_but_never_stored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    factory = FakeFactory("claude")
    provider = ClaudeExtractor(client_factory=factory)
    CachedExtractor(provider, Cache(tmp_path, "record")).extract(TRANSCRIPT)
    assert factory.factory_kwargs["api_key"] == SENTINEL
    assert_no_leak(provider, tmp_path)


# --- real SDK clients, no network: a mock transport answers every request ---


def exc_texts(exc: BaseException | None) -> list[str]:
    """str and repr of an exception and its cause/context chain."""
    texts: list[str] = []
    while exc is not None:
        texts += [str(exc), repr(exc)]
        exc = exc.__cause__ or exc.__context__
    return texts


def assert_sentinel_absent(exc: BaseException) -> None:
    assert not any(SENTINEL in t for t in exc_texts(exc))
    # The full printed traceback: covers chained exceptions and add_note() notes,
    # which is what would end up in a log
    assert SENTINEL not in "".join(traceback.format_exception(exc))


def offline_groq(**kwargs: Any) -> groq.Groq:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    http = groq.DefaultHttpxClient(transport=httpx.MockTransport(handler))
    return groq.Groq(**{**kwargs, "max_retries": 0}, http_client=http)


def offline_anthropic(**kwargs: Any) -> anthropic.Anthropic:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"error": "boom"})

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return anthropic.Anthropic(**{**kwargs, "max_retries": 0}, http_client=http)


def test_real_groq_client_does_not_expose_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL)
    provider = GroqPersona()  # default factory: the real groq.Groq
    assert SENTINEL not in repr(provider)
    assert SENTINEL not in repr(vars(provider))


def test_real_claude_client_does_not_expose_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    provider = ClaudeExtractor()  # default factory: the real anthropic.Anthropic
    assert SENTINEL not in repr(provider)
    assert SENTINEL not in repr(vars(provider))


def failing_call[P](provider: P, call: Callable[[P], object]) -> BaseException:
    """Run call(provider), expect it to raise, and return the exception."""
    with pytest.raises(Exception) as info:  # noqa: PT011  any SDK error type will do
        call(provider)
    return info.value


def test_failed_groq_call_does_not_leak_key_in_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL)
    provider = GroqPersona(client_factory=offline_groq)
    exc = failing_call(provider, lambda p: p.reply(TRANSCRIPT, None))
    assert isinstance(exc, groq.APIStatusError)  # it really went through the SDK
    assert_sentinel_absent(exc)


def test_failed_claude_call_does_not_leak_key_in_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    provider = ClaudeExtractor(client_factory=offline_anthropic)
    exc = failing_call(provider, lambda p: p.extract(TRANSCRIPT))
    assert isinstance(exc, anthropic.APIStatusError)
    assert_sentinel_absent(exc)
