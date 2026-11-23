"""Reply tidy: turns a raw persona reply into safe, speakable text.

Pure functions, no network, no keys. GroqPersona.reply calls tidy_reply on every reply.
"""

import re

from natter.providers.reply_style import style_guard
from natter.providers.reply_voice import LEADING_QUOTES, sounds_like_assistant
from natter.schema import Turn

MAX_PERSONA_CHARS = 200  # one voice request; the prompt asks for replies under this

# Used instead of any reply that would put a new number in the persona's mouth.
# No digits, plain ASCII, well under MAX_PERSONA_CHARS (a test checks all three).
SAFE_STALL = "Oh dear, the line went all crackly there. Could you say that again, love?"

# Typographic characters the model likes, mapped to plain ASCII for the voice
TYPOGRAPHIC = str.maketrans(
    {
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        "‒": "-",  # figure dash
        "―": "-",  # horizontal bar
        "‘": "'",  # left single quote
        "’": "'",  # right single quote / curly apostrophe
        "‚": "'",  # low single quote
        "‛": "'",  # reversed single quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "„": '"',  # low double quote
        "‟": '"',  # reversed double quote
        "…": "...",  # ellipsis
    }
)

# Zero-width characters: U+200B space, U+200C non-joiner, U+200D joiner, U+2060 word
# joiner, U+FEFF no-break space/BOM. isspace() is False for them, so they are mapped to
# a space here; often they stand where a real space was ("a<U+200B>b" means "a b").
ZERO_WIDTH = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF), " ")

# A dash used as a pause is spoken as a comma: an em or en dash (spaced or not), or a
# hyphen with spaces on both sides. A hyphen inside a word (KB-20931, 20-45-17) is kept.
DASH_PAUSE = re.compile(r"\s*[–—]\s*|\s+-\s+")
# Leftovers of that swap: ", ," becomes "," and " ," becomes ","
DOUBLE_COMMA = re.compile(r",(\s*,)+")
SPACE_BEFORE_COMMA = re.compile(r"\s+,")

# A missing space after punctuation. , or ; directly before any letter ("else,just"),
# ! or ? directly before a lowercase letter ("again!if"). ! or ? before a CAPITAL is a
# seam (below) and is left alone; "." belongs to the seam rule too. Digits are not
# letters, so "6,000" is untouched.
GLUED_COMMA = re.compile(r"([,;])(?=[^\W\d_])")  # [^\W\d_] means "a letter"
GLUED_BANG = re.compile(r"([!?])(?=[a-z])")

# Sentence-ending punctuation glued straight onto a capital letter: "worry.Could"
GLUED_SEAM = re.compile(r"[.!?](?=[A-Z])")
# The last sentence end inside a window: punctuation followed by a space or the end
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


# One number: digits joined by spaces, hyphens, slashes, full stops, commas or
# underscores ("12/34/56", "12.34.56", "1_2_3_4"). Compared by its digits only.
NUMBER_GROUP = re.compile(r"\d[\d\s\-/.,_]*\d")


def introduces_new_number(reply: str, transcript: list[Turn]) -> bool:
    """True if the reply has a number of 4 or more digits the caller never said."""
    said = [re.sub(r"\D", "", turn.text) for turn in transcript if turn.speaker == "scammer"]
    for group in NUMBER_GROUP.findall(reply):
        digits = re.sub(r"\D", "", group)
        if len(digits) >= 4 and not any(digits in s for s in said):
            return True
    return False


# A stock assistant refusal at the START of the reply, whatever its length. The persona
# never refuses, so this means the model broke character. Read it in parts:
#   optional apology: "I'm sorry" / "I am sorry" / "Sorry"
#   optional vocative: ONE word, letters only, so it cannot swallow a sentence
#     ("I'm sorry, love, but ..." / "Sorry dear, but ...")
#   optional , . or ! then a space
#   optional "but"
#   the refusal: I can't / I cannot / I won't / I am unable to / I'm unable to
#   the verb, in one of two shapes:
#     plain: help, assist, comply, provide, continue, or "do that"
#     narrow: say, tell, give, repeat, share, reveal, print, disclose. These are common
#       in a granny's mouth ("I can't say for certain, dear"), so they only count when
#       the refusal ENDS right after its object: optional "you" or "out", then that /
#       this / it, optional "information", then optionally "," and one word ("love"),
#       optional . or !, and the end of the reply. "I can't repeat that, my memory's
#       gone" has more words after the object, so it is kept.
# or a reply that starts "As an AI". Straight apostrophes only: tidy_reply has mapped
# the curly ones before this runs. Leading quote marks are stripped first (see below).
# "Oh I can't help with that cat" does not start with the refusal, and "I can't find my
# glasses" has a verb not on the list.
REFUSAL_OPENER = re.compile(
    r"^(?:(?:i'm sorry|i am sorry|sorry)(?:,?\s+[a-z]+)?[,.!]?\s+)?"
    r"(?:but\s+)?"
    r"(?:i can't|i cannot|i won't|i am unable to|i'm unable to)\s+"
    r"(?:(?:help|assist|comply|provide|continue|do that)\b"
    r"|(?:say|tell|give|repeat|share|reveal|print|disclose)"
    r"(?:\s+(?:you|out))?\s+(?:that|this|it)(?:\s+information)?"
    r"(?:,\s*[a-z]+)?[.!]?\s*$)"
    r"|^as an ai\b",
    re.IGNORECASE,
)


def looks_like_refusal(reply: str) -> bool:
    """True if reply opens with a stock refusal ("I'm sorry, but I can't help with that.")."""
    return REFUSAL_OPENER.search(reply.lstrip(LEADING_QUOTES)) is not None


def cut_to_limit(text: str) -> str:
    """Cut text to MAX_PERSONA_CHARS at the last sentence end, else at the last word."""
    if len(text) <= MAX_PERSONA_CHARS:
        return text
    window = text[:MAX_PERSONA_CHARS]
    ends = list(SENTENCE_END.finditer(window))
    if ends:
        return window[: ends[-1].end()]
    # No sentence end: cut before the last space so no word is split
    space = window.rfind(" ")
    return window[:space].rstrip() if space > 0 else window


def plain_spaces(text: str) -> str:
    """Turn every Unicode space and every zero-width character into an ASCII space.

    Runs before any other mapping, so a space such as U+202F in "give me" is never
    lost and the words never run together ("giveme").
    """
    text = text.translate(ZERO_WIDTH)
    # isspace() covers U+00A0, U+2009, U+202F, U+3000, newlines, tabs and the rest
    return "".join(" " if ch.isspace() else ch for ch in text)


def tidy_reply(text: str, transcript: list[Turn]) -> str:
    """Make a model reply safe and speakable. Steps run in this order."""
    # First: spaces and zero-width characters made plain spaces (see plain_spaces);
    # step 1 below collapses any run of spaces into one
    text = plain_spaces(text)
    # Then: a space after , ; ! ? glued to a following letter ("else,just" -> "else, just")
    text = GLUED_BANG.sub(r"\1 ", GLUED_COMMA.sub(r"\1 ", text))
    # 0. A glued second answer ("worry.Could you...") is dropped at the seam
    seam = GLUED_SEAM.search(text)
    if seam:
        text = text[: seam.end()]
    # 1. Plain ASCII punctuation, single spaces (split() also drops NBSP and newlines)
    text = DASH_PAUSE.sub(", ", text)  # before translate, which maps other dashes to "-"
    text = SPACE_BEFORE_COMMA.sub(",", DOUBLE_COMMA.sub(",", text))
    # strip(" ,") drops a comma left at either end by a leading or trailing dash
    text = " ".join(text.translate(TYPOGRAPHIC).split()).strip(" ,")
    # 1b. Style guards: repeated love/dear, um/uh, service offers, offers of her details
    text = style_guard(text, transcript)
    # 2. Short enough for one voice request
    text = cut_to_limit(text)
    # 3. Never let the persona voice a number the caller did not say, or break character
    # with a stock refusal. Checked on the CUT text: that is exactly what gets spoken, so
    # a long reply cannot be cut down to a refusal and slip through.
    if (
        introduces_new_number(text, transcript)
        or looks_like_refusal(text)
        or sounds_like_assistant(text)
    ):
        return SAFE_STALL
    return text
