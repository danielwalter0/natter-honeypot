"""Assistant-voice guard: catches replies where the model drops the granny and sounds
like a helpful chatbot. Pure function, no network, no keys."""

import re

# Quote marks and spaces a model may put round the whole reply: "Understood."
LEADING_QUOTES = "\"' \t\n"

# Phrases a chatbot says and a confused granny does not. \b means "at a word edge", so
# a phrase cannot match inside a longer word. Case is ignored.
#   how can/may I assist, how can I be of assistance
#   here to help, happy to help ("happy to have a chat" does not match)
#   as an AI, language model, system prompt
ASSISTANT_PHRASES = re.compile(
    r"\bhow (?:can|may) i assist\b"
    r"|\bhow can i be of assistance\b"
    r"|\bhere to help\b"
    r"|\bhappy to help\b"
    r"|\bas an ai\b"
    r"|\blanguage model\b"
    r"|\bsystem prompt\b",
    re.IGNORECASE,
)

# A reply whose FIRST word is Understood or Certainly: the word, then punctuation,
# a space or the end. "Certain sorts of biscuits" does not match (a different word).
ASSISTANT_OPENER = re.compile(r"^(?:understood|certainly)(?=[\s.,!?;:]|$)", re.IGNORECASE)


def sounds_like_assistant(reply: str) -> bool:
    """True if the reply reads like a chatbot, not the persona. Straight apostrophes only."""
    text = reply.strip()
    # The opener check ignores quote marks round the reply: "Understood."
    opener = text.lstrip(LEADING_QUOTES)
    return ASSISTANT_PHRASES.search(text) is not None or ASSISTANT_OPENER.search(opener) is not None
