"""Style guards: fixed rules that take the model's habits out of a persona reply.

Pure functions, no network. tidy_reply calls style_guard after the punctuation clean-up
and before the 200 character cut. A guard only ever removes words or whole sentences,
and never empties a reply: if nothing speakable would be left, the input comes back.
"""

import re

from natter.schema import Turn

# a. Any "love" or "dear" in one of her last two replies means no vocative this time
LOVE_OR_DEAR = re.compile(r"\b(?:love|dear)\b", re.IGNORECASE)
# ", love" / ", my dear" at the end of a clause: "Which bank, dear?" -> "Which bank?"
VOCATIVE_AFTER_COMMA = re.compile(r", (?:my )?(?:love|dear)\b(?=[,.!?]|$)", re.IGNORECASE)
# "Love, ..." / "Dear, ..." starting a sentence; the next word gets the capital letter
VOCATIVE_AT_START = re.compile(r"(^|[.!?] )(?:my )?(?:love|dear), (\w)", re.IGNORECASE)

# b. "um" or "uh" as a word of its own, with its comma. Not inside a word ("umbrella",
# "Huh") and not joined by a hyphen ("uh-huh").
FILLER = re.compile(r"(?<![\w-])(?:um|uh)(?![\w-]),?", re.IGNORECASE)

# c. A sentence that offers service, like a receptionist
SERVICE = re.compile(
    r"\b(?:do|did) you need anything else\b"
    r"|\banything else (?:you need|i can do)\b"
    r"|\bwhat else do you need\b"
    r"|\bwhat (?:should|shall|do) i do next\b"
    r"|\bwhat (?:details|information|info) do you need\b"
    r"|\bhow (?:else )?can i help\b"
    r"|\bis there anything else\b"
    # Offers to list or explain, after an off-topic question
    r"|\b(?:do you )?want the full list\b"
    r"|\bshall i list\b"
    r"|\bwould you like me to explain\b",
    re.IGNORECASE,
)

# d. A sentence offering her own details: an offer, then "my", then up to two words,
# then a kind of detail. "Do you want my grandson?" has no detail word, so it stays.
DETAILS_OFFER = re.compile(
    r"(?:(?:shall|should|can|could|will|would) i (?:read|give|tell|send) you"
    r"|i (?:can|could) (?:read|give|tell|send) you"
    r"|(?:do|would) you (?:need|want)"
    r"|do you want me to (?:read|give|tell|send) you)"
    r" my (?:\w+ ){0,2}?"
    r"(?:account|card|bank|sort code|pin|password|details|number|date of birth|address|code)\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?]) ")  # the text has single spaces by now


def _recent_vocative(transcript: list[Turn]) -> bool:
    """True if one of her last two replies said "love" or "dear"."""
    persona = [t.text for t in transcript if t.speaker == "persona"]
    return any(LOVE_OR_DEAR.search(text) for text in persona[-2:])


def _drop_vocatives(text: str) -> str:
    text = VOCATIVE_AFTER_COMMA.sub("", text)
    # Keep what came before ("" or "Right. "), and capitalise the word after the vocative
    return VOCATIVE_AT_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def _drop_sentences(text: str) -> str:
    """Rules c and d. A sentence is only dropped while another one remains."""
    sentences = SENTENCE_SPLIT.split(text)
    # d. Offers of her own details, wherever they are
    kept = [s for s in sentences if not DETAILS_OFFER.search(s)]
    sentences = kept or sentences[:1]  # all were offers: keep the first, never empty
    # c. A service offer at the end, then the one before it, and so on
    while len(sentences) > 1 and SERVICE.search(sentences[-1]):
        sentences.pop()
    return " ".join(sentences)


def _clean(text: str) -> str:
    """Mend the spacing and punctuation that a removal can leave behind."""
    text = " ".join(text.split())  # double spaces
    text = re.sub(r",(\s*,)+", ",", text)  # "Oh, , I'm" -> "Oh, I'm"
    text = re.sub(r"\s+([,.!?])", r"\1", text)  # "bank ?" -> "bank?"
    text = re.sub(r",(?=[.!?])", "", text)  # "bank,?" -> "bank?"
    text = text.strip(" ,")
    # A sentence that now starts with a small letter gets its capital back
    return re.sub(r"(^|[.!?] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def style_guard(text: str, transcript: list[Turn]) -> str:
    """Apply rules a to d. transcript is the call so far, before this reply."""
    out = text
    if _recent_vocative(transcript):
        out = _drop_vocatives(out)
    out = _drop_sentences(FILLER.sub("", out))
    if out == text:
        return text  # nothing removed: leave her words exactly as they were
    out = _clean(out)
    # Never empty: something speakable must be left, or the input comes back
    return out if any(ch.isalpha() for ch in out) else text
