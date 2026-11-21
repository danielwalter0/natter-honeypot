from pathlib import Path

from natter.audio_cache import AudioCache, CachedSpeech
from natter.providers.fakes import FakeSpeech
from natter.throttle import Throttle, ThrottledSpeech
from tests.test_audio_cache import key_fn


class FakeTime:
    """A clock we move by hand, plus a sleep that records and advances it."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make(gap: float = 7.0) -> tuple[Throttle, FakeTime]:
    t = FakeTime()
    return Throttle(gap, clock=t.clock, sleep=t.sleep), t


def test_first_call_does_not_sleep() -> None:
    throttle, t = make()
    throttle.wait()
    assert t.sleeps == []


def test_immediate_second_call_sleeps_full_gap() -> None:
    throttle, t = make()
    throttle.wait()
    throttle.wait()
    assert t.sleeps == [7.0]


def test_call_after_long_gap_does_not_sleep() -> None:
    throttle, t = make()
    throttle.wait()
    t.now += 10.0
    throttle.wait()
    assert t.sleeps == []


def test_partial_gap_sleeps_remainder() -> None:
    throttle, t = make()
    throttle.wait()
    t.now += 3.0
    throttle.wait()
    assert t.sleeps == [4.0]


def test_three_calls_sleep_a_full_gap_each_time() -> None:
    throttle, t = make()
    for _ in range(3):
        throttle.wait()  # only the sleeps move the fake clock
    assert t.sleeps == [7.0, 7.0]


def test_throttled_speech_waits_then_speaks() -> None:
    throttle, t = make()
    inner = FakeSpeech()
    speech = ThrottledSpeech(inner, throttle)
    assert speech.name == "fake-speech"
    speech.speak("a")
    speech.speak("b")
    assert inner.texts == ["a", "b"]
    assert t.sleeps == [7.0]


def test_cache_hit_does_not_wait(tmp_path: Path) -> None:
    throttle, t = make()
    inner = FakeSpeech()
    cache = AudioCache(tmp_path, "record")
    speech = CachedSpeech(ThrottledSpeech(inner, throttle), cache, key_fn)
    speech.speak("hi")  # miss: reaches the throttle (first call, no sleep)
    speech.speak("hi")  # hit: never reaches the throttle
    speech.speak("hi")
    assert inner.texts == ["hi"]
    assert t.sleeps == []
