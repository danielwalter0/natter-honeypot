"""Plain-text details for --details and --transcript. Pure formatting, no I/O."""

from typing import Any

from natter.check import Rejection
from natter.list_scoring import letters_digits, same_identifier
from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import Dossier, Turn
from natter.scoring import unwrap

LIST_FIELDS = ("identifiers", "pressure_tactics", "information_requested")


def identifier_diff(raw: dict[str, Any], dossier: Dossier) -> tuple[list[str], list[str]]:
    """(missed, extra) as "kind: value". Uses the same match rule as the identifier score."""
    expected = [(i["kind"], i["value"]) for i in raw.get("identifiers", [])]
    got = [(i.kind.value, i.value) for i in dossier.identifiers]

    def same(e: tuple[str, str], g: tuple[str, str]) -> bool:
        return same_identifier((e[0], letters_digits(e[1])), (g[0], letters_digits(g[1])))

    missed = [f"{k}: {v}" for k, v in expected if not any(same((k, v), g) for g in got)]
    extra = [f"{k}: {v}" for k, v in got if not any(same(e, (k, v)) for e in expected)]
    return missed, extra


def string_diff(raw: dict[str, Any], dossier: Dossier, name: str) -> tuple[list[str], list[str]]:
    """(missed, extra) for pressure_tactics or information_requested, by plain equality."""
    expected = [str(unwrap(item)) for item in raw.get(name, [])]
    got = [str(item.value.value) for item in getattr(dossier, name)]
    return [e for e in expected if e not in got], [g for g in got if g not in expected]


def rejection_lines(rejections: list[Rejection], turns: list[int]) -> list[str]:
    """One line per drop, e.g. "turn 4, identifiers[1]: quote not found in cited turn"."""
    lines = [f"turn {t}, {r.field}: {r.reason}" for t, r in zip(turns, rejections, strict=True)]
    return lines or ["none"]


def joined(items: list[str]) -> str:
    return "; ".join(items) if items else "none"


def details_text(
    name: str,
    raw: dict[str, Any],
    dossier: Dossier,
    rejections: list[Rejection],
    rejection_turns: list[int],
) -> str:
    """The --details section for one scored scenario."""
    lines = [f"## {name}"]
    for field in LIST_FIELDS:
        if field == "identifiers":
            missed, extra = identifier_diff(raw, dossier)
        else:
            missed, extra = string_diff(raw, dossier, field)
        lines.append(f"{field} missed: {joined(missed)}")
        lines.append(f"{field} extra: {joined(extra)}")
    drops = rejection_lines(rejections, rejection_turns)
    if drops == ["none"]:
        lines.append("rejections: none")
    else:
        lines.append("rejections:")
        lines.extend("  " + line for line in drops)
    return "\n".join(lines)


def transcript_lines(transcript: list[Turn]) -> list[str]:
    """One line per turn. A persona reply that is the safe stall line is marked."""
    lines = []
    for turn in transcript:
        mark = " [safe stall]" if turn.speaker == "persona" and turn.text == SAFE_STALL else ""
        lines.append(f"[{turn.index}] {turn.speaker}: {turn.text}{mark}")
    return lines
