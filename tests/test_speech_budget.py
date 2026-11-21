"""Tests for the speech request budget."""

from pathlib import Path

import pytest

from natter.audio_cache import AudioCache, CachedSpeech
from natter.audio_key import speech_key
from natter.providers.fakes import FakeSpeech
from natter.speech_budget import BudgetedSpeech, SpeechBudgetUsed


class ProviderDown(Exception):
    """A stand-in provider error (not a RuntimeError, which NotImplementedError is)."""


class FailingSpeech:
    """Always raises, and counts how often it was called."""

    name = "failing-speech"

    def __init__(self) -> None:
        self.calls = 0

    def speak(self, text: str) -> bytes:
        self.calls += 1
        raise ProviderDown("provider down")


@pytest.mark.parametrize("bad", [-1, 2.5, True, "3", None])
def test_bad_max_requests_raise(bad: object) -> None:
    with pytest.raises(ValueError):
        BudgetedSpeech(FakeSpeech(), bad)  # type: ignore[arg-type]


def test_init_copies_name_and_starts_at_zero() -> None:
    budget = BudgetedSpeech(FakeSpeech(), 3)
    assert budget.name == "fake-speech"
    assert budget.max_requests == 3
    assert budget.used == 0


def test_each_real_call_counts_and_returns_inner_audio() -> None:
    inner = FakeSpeech()
    budget = BudgetedSpeech(inner, 3)
    assert budget.speak("one") == inner.speak("x")  # same bytes as the inner provider
    budget.speak("two")
    assert budget.used == 2
    assert inner.texts == ["one", "x", "two"]


def test_refuses_at_the_cap_without_calling_inner() -> None:
    inner = FakeSpeech()
    budget = BudgetedSpeech(inner, 2)
    budget.speak("one")
    budget.speak("two")
    with pytest.raises(SpeechBudgetUsed):
        budget.speak("three")
    assert inner.texts == ["one", "two"]  # the third never reached inner
    assert budget.used == 2


def test_zero_budget_refuses_the_first_call() -> None:
    inner = FakeSpeech()
    budget = BudgetedSpeech(inner, 0)
    with pytest.raises(SpeechBudgetUsed):
        budget.speak("one")
    assert inner.texts == []
    assert budget.used == 0


def test_a_failing_inner_still_counts() -> None:
    inner = FailingSpeech()
    budget = BudgetedSpeech(inner, 2)
    with pytest.raises(ProviderDown):  # the inner error propagates unchanged
        budget.speak("one")
    assert budget.used == 1
    assert inner.calls == 1
    with pytest.raises(ProviderDown):
        budget.speak("two")
    with pytest.raises(SpeechBudgetUsed):  # both failures used up the budget
        budget.speak("three")
    assert inner.calls == 2


def test_cache_hit_never_counts(tmp_path: Path) -> None:
    inner = FakeSpeech()
    budget = BudgetedSpeech(inner, 5)
    cached = CachedSpeech(budget, AudioCache(tmp_path, "record"), speech_key)
    first = cached.speak("same line")
    second = cached.speak("same line")
    assert first == second
    assert budget.used == 1  # the repeat came from the cache
    assert inner.texts == ["same line"]
