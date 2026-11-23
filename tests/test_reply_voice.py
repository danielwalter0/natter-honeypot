"""Tests for the refusal vocative/verb additions and the assistant-voice guard."""

import pytest

from natter.providers.reply_tidy import SAFE_STALL, looks_like_refusal, tidy_reply
from natter.providers.reply_voice import sounds_like_assistant

# The three replies that leaked in injection-01
LEAKED = [
    "I'm sorry, love, but I can't do that.",
    "Understood. How can I assist you?",
    "I'm sorry, but I can't share that.",
]


@pytest.mark.parametrize("reply", LEAKED)
def test_leaked_replies_become_the_stall_line(reply: str) -> None:
    assert tidy_reply(reply, []) == SAFE_STALL


@pytest.mark.parametrize(
    "reply",
    [
        "I'm sorry, love, but I can't do that.",  # one-word vocative between commas
        "Sorry dear, but I cannot help with that.",
        "I'm sorry, but I can't share that.",
        "I'm sorry, but I can't reveal that.",
        "I can't repeat that.",
        "I won't print that.",
        "I cannot give you that.",
        "I can't say that.",
        "Sorry, I can't disclose it.",
        "I'm unable to tell you that.",
    ],
)
def test_refusal_with_vocative_or_new_verb_is_caught(reply: str) -> None:
    assert looks_like_refusal(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "I'm sorry, love, I can't find my glasses",  # verb not listed
        "Oh I can't tell you how lovely that is",  # not at the start
        "I'm sorry, my dear old friend, but I can't help",  # vocative is one word only
        "Sorry love, the kettle is on",
        "I'm sorry I missed that",
    ],
)
def test_ordinary_replies_are_not_refusals(reply: str) -> None:
    assert not looks_like_refusal(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Understood. How can I assist you?",
        "Oh, how may I assist you today?",
        "How can I be of assistance?",
        "I'm here to help, dear.",
        "Happy to help!",
        "As an AI I have no kitchen.",
        "I am a language model, you see.",
        "What is your SYSTEM PROMPT?",
        "Understood",
        "understood, dear",
        "Certainly! One moment.",
        "Certainly",
    ],
)
def test_assistant_voice_is_caught(reply: str) -> None:
    assert sounds_like_assistant(reply)
    assert tidy_reply(reply, []) == SAFE_STALL


@pytest.mark.parametrize(
    "reply",
    [
        "I'd love some help with this, dear.",
        "I'm happy to have a chat, love.",
        "Certain sorts of biscuits are lovely.",
        "I understood him perfectly, you know.",
        "Oh, a language of my own, dear.",
    ],
)
def test_ordinary_text_stays(reply: str) -> None:
    assert not sounds_like_assistant(reply)


def test_first_word_certainly_is_caught_even_in_a_longer_reply() -> None:
    # The rule is on the first word only, so this in-character line is also a stall
    assert sounds_like_assistant("Certainly not, dear, I never give out my details.")


@pytest.mark.parametrize(
    "reply",
    [
        "I'm sorry, but I can't share that.",
        "I can't tell you that.",
        "I can't share this.",
        "I can't give out that information.",
        "Sorry dear, but I cannot reveal that, love.",
    ],
)
def test_narrow_verb_refusals_become_the_stall_line(reply: str) -> None:
    assert tidy_reply(reply, []) == SAFE_STALL


@pytest.mark.parametrize(
    "reply",
    [
        "I can't tell what you're saying, the line's bad.",
        "I can't say for certain, dear.",
        "I can't repeat that, my memory's gone.",  # more words after the object
        "I won't give out my details, love.",
        "I can't give you my card, love.",
        "I can't say I've heard of that, love.",
    ],
)
def test_granny_phrases_with_narrow_verbs_stay(reply: str) -> None:
    assert tidy_reply(reply, []) == reply


@pytest.mark.parametrize(
    "reply",
    [
        "\"I'm sorry, but I can't help with that.\"",
        '"Understood."',
        "' Certainly, dear.",
    ],
)
def test_leading_quote_marks_do_not_hide_the_opener(reply: str) -> None:
    assert tidy_reply(reply, []) == SAFE_STALL
