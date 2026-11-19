"""Tests for the persona reply tidy step and the new-number guard."""

from pathlib import Path

import pytest

from natter.providers import groq_persona, reply_tidy
from natter.providers.groq_persona import SYSTEM_PROMPT, GroqPersona
from natter.providers.reply_tidy import (
    MAX_PERSONA_CHARS,
    SAFE_STALL,
    looks_like_refusal,
    plain_spaces,
    tidy_reply,
)
from natter.schema import Turn
from tests.fake_clients import FakeFactory, groq_response

# Captured before any test patches the module attribute
REAL_GUARD = reply_tidy.introduces_new_number

CALLER_NUMBER = "If we get disconnected, call me back directly on 07700 900482 and ask for James."


def caller(*texts: str) -> list[Turn]:
    return [Turn(index=i, speaker="scammer", text=t) for i, t in enumerate(texts)]


@pytest.fixture
def no_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test-local stand-in so tidy tests do not depend on the owner's guard
    monkeypatch.setattr(reply_tidy, "introduces_new_number", lambda r, t: False)


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


# --- a missing space after , ; ! ? (runs after plain_spaces, before the seam cut) ---


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("Anything else,just say.", "Anything else, just say."),  # comma, any letter
        ("Yes;that is right.", "Yes; that is right."),  # semicolon, any letter
        ("Say it again!if you would.", "Say it again! if you would."),  # ! before lowercase
        ("Really?yes, dear.", "Really? yes, dear."),  # ? before lowercase
    ],
)
def test_space_is_added_after_glued_punctuation(no_guard: None, raw: str, spoken: str) -> None:
    assert tidy_reply(raw, []) == spoken


def test_bang_before_a_capital_is_still_a_seam(no_guard: None) -> None:
    # ! or ? glued to a capital stays the seam rule's job: the second answer is cut
    assert tidy_reply("Say it again!If you would.", []) == "Say it again!"


@pytest.mark.parametrize("text", ["It was 6,000 pounds.", "Sort code 20-45-17.", "Ref KB-20931."])
def test_numbers_and_codes_get_no_space(no_guard: None, text: str) -> None:
    assert tidy_reply(text, []) == text


# --- step 1: typographic characters and whitespace ---


def test_typographic_punctuation_becomes_ascii(no_guard: None) -> None:
    raw = "It\u2019s fine \u2014 don\u2019t worry \u201cdear\u201d \u2013 the kettle\u2026"
    assert tidy_reply(raw, []) == "It's fine, don't worry \"dear\", the kettle..."


@pytest.mark.parametrize(
    ("raw", "spoken"),
    [
        ("kettle\u2014tiny chaos", "kettle, tiny chaos"),  # em dash
        ("kettle \u2013 tiny chaos", "kettle, tiny chaos"),  # spaced en dash
        ("kettle - tiny chaos", "kettle, tiny chaos"),  # spaced hyphen
        ("Oh, \u2014 well", "Oh, well"),  # no ", ," left behind
        ("kettle \u2014, tiny", "kettle, tiny"),  # no " ," left behind
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
        ("Could you give\u202fme a moment?", "Could you give me a moment?"),  # narrow NBSP
        ("If\u00a0you would, dear.", "If you would, dear."),  # no-break space
        ("a\u2009b", "a b"),  # thin space
        ("a\u3000b", "a b"),  # ideographic space
        ("a\u200bb", "a b"),  # zero-width space
        ("a\u200c\u200d\u2060\ufeffb", "a b"),  # the rest; the run becomes one space
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
    assert tidy_reply("  Oh \n\t dear,\u00a0the   cat.  ", []) == "Oh dear, the cat."


# --- step 2: a new number is replaced by the fixed stall line ---


def test_new_number_gives_the_stall_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reply_tidy, "introduces_new_number", lambda r, t: True)
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
    raw = "Oh, I\u2019m not sure.Sure thing, here it is."
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


# --- NATTER_RAW_LOG: the raw reply, before any tidying, for debugging ---


def test_raw_log_gets_the_untidied_reply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_guard: None
) -> None:
    log = tmp_path / "raw.log"
    monkeypatch.setenv("NATTER_RAW_LOG", str(log))
    raw = "Oh\u202fdear\u2014the kettle.Sure thing"
    persona(monkeypatch, raw).reply(caller("hi"), None)
    persona(monkeypatch, "Second reply.").reply(caller("hi"), None)
    # One repr line per reply, appended, exactly as the model sent it
    assert log.read_text(encoding="utf-8").splitlines() == [repr(raw), repr("Second reply.")]


def test_no_raw_log_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_guard: None
) -> None:
    monkeypatch.delenv("NATTER_RAW_LOG", raising=False)
    monkeypatch.chdir(tmp_path)  # anything written to a relative path would land here
    assert persona(monkeypatch, "Hello dear.").reply(caller("hi"), None) == "Hello dear."
    assert list(tmp_path.iterdir()) == []


# --- regressions from spike_out/raw_replies.txt (\u escapes, no invisible characters) ---

RAW_LET_ME_SEE = (
    "Sure, I\u2019ll stay put, mum's about the new kettle. I\u2019ll keep this between us, "
    "not even tell the neighbour. Let me see\u2026 could you repeat the code? "
    "I\u2019m sure I misheard."
)
RAW_GRANDSON = (
    "Ah, that\u2019s helpful! Please give me a number to ring you back on \u2013 just in case "
    "I need to double\u2011check with my grandson. I\u2019ll be on the line till you\u2019re done."
)


def test_ellipsis_then_space_keeps_the_space(no_guard: None) -> None:
    assert "Let me see... could you repeat the code?" in tidy_reply(RAW_LET_ME_SEE, [])


def test_full_stop_then_curly_apostrophe_keeps_the_space(no_guard: None) -> None:
    out = tidy_reply(RAW_GRANDSON, [])
    assert "my grandson. I'll be on the line" in out
    assert "double-check" in out  # U+2011 non-breaking hyphen becomes "-"


# --- stock refusals are replaced by the stall line ---


@pytest.mark.parametrize(
    "refusal",
    [
        "I'm sorry, but I can't help with that.",
        "I\u2019m sorry, but I can\u2019t help with that.",  # curly apostrophes, as sent
        "I am sorry, but I cannot do that.",
        "I can't comply with that request.",
    ],
)
def test_stock_refusal_becomes_the_stall_line(no_guard: None, refusal: str) -> None:
    assert looks_like_refusal(refusal.replace("\u2019", "'"))
    assert tidy_reply(refusal, []) == SAFE_STALL


def test_in_character_cannot_is_not_a_refusal(no_guard: None) -> None:
    assert tidy_reply("I can't find my glasses, dear", []) == "I can't find my glasses, dear"


def test_long_in_character_reply_with_the_phrase_is_kept(no_guard: None) -> None:
    long = (
        "Oh, my grandson always says the bank can't help with that sort of thing, "
        "but let me find my glasses and have a look for the letter, dear."
    )
    assert len(long) >= 80
    assert tidy_reply(long, []) == long


def test_prompt_has_the_no_robot_talk_rule() -> None:
    assert "Never mention robots, AI or being real unless he asks you directly." in (SYSTEM_PROMPT)
    assert "If he does, stay vague and chatty and change the subject." in SYSTEM_PROMPT
    assert "act puzzled and amused" not in SYSTEM_PROMPT  # the old rule is folded in


# --- refusals are matched at the start, whatever the length; guards run after the cut ---

LONG_TAIL = (
    " Oh the kettle is going and the cat is on the table and my grandson said the man"
    " next door has been cutting the hedge all morning love and I never got a wink of sleep"
)


@pytest.mark.parametrize(
    "refusal",
    [
        "I'm sorry, but I can't help with that. Is there anything else I can help you with today?",
        "I'm sorry, but I can't help with that." + LONG_TAIL,  # over 200: cut, then caught
        "I'm sorry, I can't provide that.",
        "I won't do that",
        "As an AI language model, I cannot...",
        "Sorry, but I am unable to continue.",
        "I'm unable to assist with that request.",
    ],
)
def test_refusal_at_the_start_becomes_the_stall_line(no_guard: None, refusal: str) -> None:
    assert tidy_reply(refusal, []) == SAFE_STALL


def test_long_refusal_is_over_the_limit_before_the_cut() -> None:
    # Guards the test above: this case only means something if the cut runs first
    assert len("I'm sorry, but I can't help with that." + LONG_TAIL) > MAX_PERSONA_CHARS


@pytest.mark.parametrize(
    "reply",
    ["Oh I can't help with that cat, she keeps scratching!", "I can't find my glasses, dear"],
)
def test_in_character_replies_are_not_refusals(no_guard: None, reply: str) -> None:
    assert tidy_reply(reply, []) == reply


def test_number_past_the_cut_is_not_voiced_so_not_guarded() -> None:
    # The number guard runs on the cut text: a number the cut removes never reaches the voice
    text = "Oh dear, the kettle is boiling and the cat wants feeding." + LONG_TAIL + " 4929 1234"
    out = tidy_reply(text, [])
    assert out != SAFE_STALL and "4929" not in out


# --- one number may be joined by spaces, hyphens, slashes, full stops, commas, underscores ---


@pytest.mark.parametrize(
    ("form", "caller_said"),
    [
        ("12/34/56", "12-34-56"),
        ("12.34.56", "12-34-56"),
        ("12,34,56", "12-34-56"),
        ("1_2_3_4", "1-2-3-4"),
        ("12 34 56", "12-34-56"),
    ],
)
def test_joined_digits_count_as_one_number(form: str, caller_said: str) -> None:
    reply = f"Is it {form}, love?"
    assert REAL_GUARD(reply, caller("What is your sort code?")) is True  # never said
    assert REAL_GUARD(reply, caller(f"The sort code is {caller_said}.")) is False
