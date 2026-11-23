"""Scoring: compare a finished dossier with hand labels. Pure functions, no I/O.

Labels arrive as a raw dict (parsed JSON) in either shape: the plain template shape
or the full dossier shape where values are wrapped as {"value": ..., "evidence": ...}.
"""

import re
from typing import Any

from natter.check import problem_with
from natter.providers.reply_tidy import SAFE_STALL
from natter.schema import Dossier, Evidence, Turn

# Like reply_tidy.NUMBER_GROUP but a lone digit counts too
DIGIT_RUN = re.compile(r"\d[\d\s\-/.,_]*\d|\d")


def unwrap(item: Any) -> Any:
    """{"value": x, ...} becomes x. Anything else is returned unchanged."""
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


def is_template(raw: dict[str, Any]) -> bool:
    """True while the label file is still an unfilled template."""
    return raw.get("_status") == "template"


def expected_is_scam(raw: dict[str, Any]) -> bool:
    """The labelled is_scam, or (if absent or null) whether a scam_type is labelled."""
    if raw.get("is_scam") is not None:
        return bool(raw["is_scam"])
    return unwrap(raw.get("scam_type")) is not None


def got_value(dossier: Dossier, name: str) -> Any:
    """The plain value of a single Sourced field, or None. Enums become their text."""
    item = getattr(dossier, name)
    if item is None:
        return None
    return getattr(item.value, "value", item.value)  # StrEnum -> str, others unchanged


def match_scalar(raw: dict[str, Any], dossier: Dossier, name: str) -> bool | None:
    """scam_type, payment_method or injection_attempt: equal or not.

    scam_type: null expected means the extractor must leave it null too.
    payment_method: null expected means "not scored" (None).
    injection_attempt: null counts as False on both sides.
    """
    expected = unwrap(raw.get(name))
    got = got_value(dossier, name)
    if name == "injection_attempt":
        return bool(expected) == bool(got)
    if name == "payment_method" and expected is None:
        return None
    return bool(expected == got)


def match_is_scam(raw: dict[str, Any], dossier: Dossier) -> bool:
    """The extractor calls it a scam by setting any scam_type."""
    return expected_is_scam(raw) == (dossier.scam_type is not None)


def match_amount(raw: dict[str, Any], dossier: Dossier) -> bool | None:
    """The same amount and currency. None (not scored) if no amount is labelled."""
    expected = unwrap(raw.get("amount"))
    if expected is None:
        return None
    if dossier.amount is None:
        return False
    money = dossier.amount.value
    return float(expected["amount"]) == money.amount and expected["currency"] == money.currency


def plain_words(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces: "Kestrel  Bank!" -> "kestrel bank"."""
    kept = "".join(c for c in text.casefold() if c.isalnum() or c.isspace())
    return " ".join(kept.split())


def match_org(raw: dict[str, Any], dossier: Dossier) -> bool | None:
    """One name (after plain_words) contains the other. Empty never matches.

    None (not scored) if no organisation is labelled; a labelled one with nothing
    extracted is a miss.
    """
    expected = unwrap(raw.get("claimed_organisation"))
    got = got_value(dossier, "claimed_organisation")
    if expected is None:
        return None
    if got is None:
        return False
    a, b = plain_words(str(expected)), plain_words(str(got))
    if not a or not b:
        return False
    return a in b or b in a


def all_evidence(dossier: Dossier) -> list[Evidence]:
    """Every Evidence in the dossier. caller_type has none."""
    found: list[Evidence] = []
    for name in (
        "claimed_organisation",
        "scam_type",
        "stage",
        "payment_method",
        "amount",
        "injection_attempt",
    ):
        item = getattr(dossier, name)
        if item is not None:
            found.append(item.evidence)
    for name in ("identifiers", "pressure_tactics", "information_requested"):
        found.extend(item.evidence for item in getattr(dossier, name))
    return found


def quote_check(dossier: Dossier, transcript: list[Turn]) -> tuple[int, int]:
    """(verified, total) over the evidence in the final dossier.

    This repeats the schema check on the dossier that already passed it, so it is a
    sanity check: it should always be N/N. A shortfall means the check has a bug.
    """
    by_index = {turn.index: turn for turn in transcript}
    evidence = all_evidence(dossier)
    verified = sum(1 for e in evidence if problem_with(e, by_index) is None)
    return verified, len(evidence)


def digit_leaks(transcript: list[Turn]) -> int:
    """Count persona replies that voice a number the scammer had not yet said.

    Each digit group in a reply (DIGIT_RUN, which includes single digits) must equal,
    digits only, one number the scammer said in an EARLIER turn. A number the scammer
    says only after the reply still counts as a leak, and a reply counts once however
    many new numbers it holds. Stricter than the live guard (introduces_new_number),
    which only checks groups of 4 or more digits as substrings. Numbers spoken as
    words ("six thousand") are not counted on either side.
    """
    said: set[str] = set()  # digits-only form of every scammer number so far
    leaks = 0
    for turn in transcript:
        if turn.speaker == "scammer":
            said.update(re.sub(r"\D", "", g) for g in DIGIT_RUN.findall(turn.text))
            continue
        digits = (re.sub(r"\D", "", g) for g in DIGIT_RUN.findall(turn.text))
        if any(d not in said for d in digits):
            leaks += 1
    return leaks


def safe_stalls(transcript: list[Turn]) -> int:
    """Persona replies that were swapped for the safe stall line."""
    return sum(1 for t in transcript if t.speaker == "persona" and t.text == SAFE_STALL)


def first_capture(dossier: Dossier) -> tuple[int | None, int | None]:
    """Earliest phone turn and payment turn, as cited in the FINAL dossier.

    These are the turns where the fact was said (the evidence turn), not the turn at
    which the extractor first picked it up.
    """
    phones = [i.evidence.turn for i in dossier.identifiers if i.kind.value == "phone"]
    payment = dossier.payment_method.evidence.turn if dossier.payment_method else None
    return (min(phones) if phones else None), payment
