"""A hard cap on real speech requests, so a bug cannot burn the Groq quota.

Intended stack (the order matters):

    CachedSpeech(
        BudgetedSpeech(ThrottledSpeech(GroqSpeech(), Throttle(7.0)), 15),
        AudioCache(..., "record"),
        speech_key,
    )

BudgetedSpeech sits INSIDE the cache, so a cache hit never reaches it and never
counts. It sits OUTSIDE the throttle, so a line over the budget is refused at
once instead of waiting for the throttle first.
"""

from natter.providers.base import Speech


class SpeechBudgetUsed(Exception):
    """Raised when the request budget is spent. No real request was made."""


class BudgetedSpeech:
    """Lets at most max_requests calls through to the inner Speech. Satisfies Speech."""

    def __init__(self, inner: Speech, max_requests: int) -> None:
        if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 0:
            raise ValueError("max_requests must be a whole number, zero or more")
        self.inner = inner
        self.max_requests = max_requests
        self.used = 0  # real requests started so far
        self.name = inner.name

    def speak(self, text: str) -> bytes:
        """Refuse with SpeechBudgetUsed if used >= max_requests (inner is not called).

        Otherwise add 1 to used BEFORE calling inner (a failed request still costs
        Groq quota), then return inner.speak(text). An inner error propagates and
        still counts.
        """
        if self.used >= self.max_requests:
            raise SpeechBudgetUsed("speech budget used up")
        self.used += 1
        return self.inner.speak(text)
