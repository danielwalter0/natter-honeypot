"""Keeps real speech calls under the provider's rate limit."""

import time
from collections.abc import Callable

from natter.providers.base import Speech


class Throttle:
    """Makes sure at least min_gap_s passes between calls to wait()."""

    def __init__(
        self,
        min_gap_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_gap_s = min_gap_s
        self.clock = clock
        self.sleep = sleep
        self.last: float | None = None  # time of the previous call, if any

    def wait(self) -> None:
        if self.last is not None:
            remaining = self.min_gap_s - (self.clock() - self.last)
            if remaining > 0:
                self.sleep(remaining)
        self.last = self.clock()


class ThrottledSpeech:
    """Waits its turn, then speaks. Satisfies Speech.

    Put it INSIDE CachedSpeech so a cache hit never waits:
    CachedSpeech(ThrottledSpeech(GroqSpeech(), Throttle(7.0)), ...).
    With a 7 s gap at most 9 requests can start in any 60 s window, still under 10 RPM.
    """

    def __init__(self, inner: Speech, throttle: Throttle) -> None:
        self.inner = inner
        self.throttle = throttle
        self.name = inner.name

    def speak(self, text: str) -> bytes:
        self.throttle.wait()
        return self.inner.speak(text)
