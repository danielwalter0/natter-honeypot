"""Small builders shared by the scoring tests."""

from natter.schema import Evidence, Sourced, Turn


def ev(turn: int, quote: str) -> Evidence:
    return Evidence(turn=turn, quote=quote, confidence=0.9)


def sourced(value: object, turn: int = 0, quote: str = "hello there") -> Sourced:  # type: ignore[type-arg]
    return Sourced(value=value, evidence=ev(turn, quote))


def turns(*pairs: tuple[str, str]) -> list[Turn]:
    return [Turn(index=i, speaker=s, text=t) for i, (s, t) in enumerate(pairs)]
