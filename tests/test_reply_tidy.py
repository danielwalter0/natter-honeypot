"""Tests for the persona reply tidy step and the new-number guard."""

import pytest

from natter.providers import groq_persona
from natter.providers.groq_persona import (
    MAX_PERSONA_CHARS,
    SAFE_STALL,
    SYSTEM_PROMPT,
    GroqPersona,
    plain_spaces,
    tidy_reply,
)
from natter.schema import Turn
from tests.fake_clients import FakeFactory, groq_response

# Captured before any test patches the module attribute
REAL_GUARD = groq_persona.introduces_new_number

CALLER_NUMBER = "If we get disconnected, call me back directly on 07700 900482 and ask for James."


def caller(*texts: str) -> list[Turn]:
    return [Turn(index=i, speaker="scammer", text=t) for i, t in enumerate(texts)]


@pytest.fixture
def no_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test-local stand-in so tidy tests do not depend on the owner's guard
    monkeypatch.setattr(groq_persona, "introduces_new_number", lambda r, t: False)


# --- introduces_new_number: the owner writes it; red until then ---


def test_guard_no_digits_is_not_new() -> None:
    assert REAL_GUARD("Oh, let me find my glasses, dear.", caller(CALLER_NUMBER)) is False


def test_guard_number_the_caller_said_is_allowed() -> None:
    reply = "So that was 07700 900482, was it, love?"
    assert REAL_GUARD(reply, caller(CALLER_NUMBER)) is False


def test_guard_caller_number_with_different_spacing_is_allowed() -> None:
    # Design choice: numbers are compared by their digits only
    assert REAL_GUARD("Is it 07700900482?", caller(CALLER_NUMBER)) is False


def test_guard_invented_number_is_new() -> None:
    assert REAL_GUARD("My PIN is 1234, dear.", caller(CALLER_NUMBER)) is True


def test_guard_number_only_the_persona_said_is_new() -> None:
    # The persona cannot launder its own invented number by repeating it
    transcript = [
        Turn(index=0, speaker="scammer", text="What is the code?"),
        Turn(index=1, speaker="persona", text="Is it 4471?"),
    ]
    assert REAL_GUARD("Yes, 4471, that's it.", transcript) is True


# --- step 0: a glued second answer is cut at the seam ---


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        (
            "Oh no, don't worry.Could you just tell me the code again?",
            "Oh no, don't worry.",
        ),
        ("Is that really you, yes?Sure thing, dear, here it is.", "Is that really you, yes?"),
        ("Well I never!Here you go.", "Well I never!"),
        ("Oh dear...Could you repeat that?", "Oh dear..."),
    ],
)
def test_glued_second_answer_is_dropped(no_guard: None, raw: str, kept: str) -> None:
    assert tidy_reply(raw, []) == kept


def test_normal_sentence_gap_is_not_a_seam(no_guard: None) -> None:
    text = "Oh no, don't worry. Could you say that again?"
    assert tidy_reply(text, []) == text


# --- step 1: typographic characters and whitespace ---


def test_typographic_punctuation_becomes_ascii(no_guard: None) -> None:
    raw = "It’s fine — don’t worry “dear” – the kettle…"
    assert tidy_reply(raw, []) == "It's fine, don't worry \"dear\", the kettle..."


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("kettle—tiny chaos", "kettle, tiny chaos"),  # em dash
        ("kettle – tiny chaos", "kettle, tiny chaos"),  # spaced en dash
        ("kettle - tiny chaos", "kettle, tiny chaos"),  # spaced hyphen
        ("Oh, — well", "Oh, well"),  # no ", ," left behind
        ("kettle —, tiny", "kettle, tiny"),  # no " ," left behind
    ],
)
def test_dash_pause_becomes_a_comma(no_guard: None, raw: str, spoken: str) -> None:
    assert tidy_reply(raw, []) == spoken


@pytest.mark.parametrize("word", ["KB-20931", "20-45-17", "well-known"])
def test_hyphen_inside_a_word_is_kept(no_guard: None, word: str) -> None:
    assert tidy_reply(f"It was {word}, dear.", []) == f"It was {word}, dear."


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("Could you give me a moment?", "Could you give me a moment?"),  # narrow NBSP
        ("If you would, dear.", "If you would, dear."),  # no-break space
        ("a b", "a b"),  # thin space
        ("a　b", "a b"),  # ideographic space
        ("a​b", "ab"),  # zero-width space
        ("a‌‍⁠﻿b", "ab"),  # the other zero-width characters
    ],
)
def test_unicode_spaces_become_spaces_and_zero_width_goes(
    no_guard: None, raw: str, spoken: str
) -> None:
    assert tidy_reply(raw, []) == spoken


def test_every_isspace_character_becomes_a_space() -> None:
    # Checks the helper over all of Unicode, so no space character is ever deleted
    spaces = [chr(c) for c in range(0x110000) if chr(c).isspace()]
    assert all(plain_spaces(f"a{ch}b") == "a b" for ch in spaces)


def test_whitespace_is_collapsed(no_guard: None) -> None:
    assert tidy_reply("  Oh \n\t dear, the   cat.  ", []) == "Oh dear, the cat."


# --- step 2: a new number is replaced by the fixed stall line ---


def test_new_number_gives_the_stall_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(groq_persona, "introduces_new_number", lambda r, t: True)
    assert tidy_reply("My card number is 4929 1234 5678 9012.", []) == SAFE_STALL


def test_stall_line_is_safe_on_its_own() -> None:
    assert len(SAFE_STALL) <= MAX_PERSONA_CHARS
    assert not any(ch.isdigit() for ch in SAFE_STALL)
    assert SAFE_STALL.isascii()


# --- step 3: cut to MAX_PERSONA_CHARS ---


def test_short_reply_is_unchanged(no_guard: None) -> None:
    assert tidy_reply("Hello dear.", []) == "Hello dear."


def test_long_reply_is_cut_at_a_sentence_boundary(no_guard: None) -> None:
    first = "Oh, the kettle has just boiled and the cat is on the table again."
    raw = f"{first} " + "And then my grandson said something about the bank, " * 5 + "dear."
    result = tidy_reply(raw, [])
    assert len(result) <= MAX_PERSONA_CHARS
    assert result == first


def test_long_reply_without_sentence_end_is_cut_at_a_word(no_guard: None) -> None:
    raw = "and the kettle " * 30  # 450 characters, no . ! or ?
    result = tidy_reply(raw, [])
    assert len(result) <= MAX_PERSONA_CHARS
    assert raw.startswith(result) and raw[len(result)] == " "  # ends on a whole word


# --- the tidy runs inside GroqPersona.reply ---


def persona(monkeypatch: pytest.MonkeyPatch, text: str) -> GroqPersona:
    monkeypatch.setattr(groq_persona, "build_messages", lambda t, g: [{"role": "system"}])
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    return GroqPersona(client_factory=FakeFactory("groq", groq_response(text)))


def test_reply_is_tidied(monkeypatch: pytest.MonkeyPatch, no_guard: None) -> None:
    raw = "Oh, I’m not sure.Sure thing, here it is."
    assert persona(monkeypatch, raw).reply(caller("hi"), None) == "Oh, I'm not sure."


def test_reply_may_repeat_the_callers_number(monkeypatch: pytest.MonkeyPatch) -> None:
    # Uses the owner's real guard, so it is red until introduces_new_number exists
    raw = "Was that 07700 900482, love?"
    assert persona(monkeypatch, raw).reply(caller(CALLER_NUMBER), None) == raw


def test_prompt_has_the_variety_rules() -> None:
    assert "Do not mention the same tangent twice in a row." in SYSTEM_PROMPT
    assert "Vary your excuses." in SYSTEM_PROMPT
    assert "If you have already asked for something, do something else this turn." in (
        SYSTEM_PROMPT
    )
