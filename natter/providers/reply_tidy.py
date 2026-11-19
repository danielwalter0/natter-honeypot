"""Reply tidy: turns a raw persona reply into safe, speakable text.

Pure functions, no network, no keys. GroqPersona.reply calls tidy_reply on every reply.
"""

import re

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


def introduces_new_number(reply: str, transcript: list[Turn]) -> bool:
    """True if the reply has a number of 4 or more digits the caller never said."""
    said = [re.sub(r"\D", "", turn.text) for turn in transcript if turn.speaker == "scammer"]
    for group in re.findall(r"\d[\d\s-]*\d", reply):
        digits = re.sub(r"\D", "", group)
        if len(digits) >= 4 and not any(digits in s for s in said):
            return True
    return False


# Stock assistant refusals. The persona never refuses, so one of these means the model
# broke character. Lower case, straight apostrophes (tidy_reply has mapped curly ones).
REFUSAL_PHRASES = (
    "can't help with that",
    "cannot help with that",
    "can't assist",
    "cannot assist",
    "can't comply",
    "cannot comply",
    "i'm sorry, but i can't",
    "i am sorry, but i cannot",
)
REFUSAL_MAX_CHARS = 80  # a stock refusal is short; a long reply is the granny talking


def looks_like_refusal(reply: str) -> bool:
    """True if reply is a short stock refusal ("I'm sorry, but I can't help with that.")."""
    text = reply.lower()
    return len(text) < REFUSAL_MAX_CHARS and any(phrase in text for phrase in REFUSAL_PHRASES)


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
    # 2. Never let the persona voice a number the caller did not say, or break
    # character with a stock refusal. Runs after step 1, so apostrophes are straight.
    if introduces_new_number(text, transcript) or looks_like_refusal(text):
        return SAFE_STALL
    # 3. Short enough for one voice request
    return cut_to_limit(text)
