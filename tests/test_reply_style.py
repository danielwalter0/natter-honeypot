"""Tests for the style guards: before and after strings for each rule. No network."""

import pytest

from natter.providers.reply_style import style_guard
from natter.providers.reply_tidy import MAX_PERSONA_CHARS, SAFE_STALL, tidy_reply
from natter.schema import Turn


def call(*persona_replies: str) -> list[Turn]:
    """A transcript where the scammer and the persona take turns, ending on the scammer."""
    turns: list[Turn] = []
    for reply in persona_replies:
        turns.append(Turn(index=len(turns), speaker="scammer", text="Hello?"))
        turns.append(Turn(index=len(turns), speaker="persona", text=reply))
    turns.append(Turn(index=len(turns), speaker="scammer", text="Go on."))
    return turns


# ---- a. vocatives: no "love" or "dear" if one of her last two replies had one


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Which bank, dear?", "Which bank?"),
        ("Go on then, love.", "Go on then."),
        ("Dear, I don't follow.", "I don't follow."),
        ("Oh, love, say that again.", "Oh, say that again."),
        ("Yes, my dear, I'm here.", "Yes, I'm here."),
        ("Right. Love, which bank?", "Right. Which bank?"),
    ],
)
def test_vocative_is_removed_after_a_recent_one(before: str, after: str) -> None:
    assert style_guard(before, call("Hello, love.", "Which one?")) == after


def test_vocative_is_kept_when_the_last_two_replies_had_none() -> None:
    transcript = call("Oh, hello dear.", "Which one?", "I see.")  # dear was three back
    assert style_guard("Which bank, love?", transcript) == "Which bank, love?"


def test_love_that_is_not_a_vocative_is_kept() -> None:
    assert style_guard("I'd love a cup of tea.", call("Go on, dear.")) == "I'd love a cup of tea."


# ---- b. "um" and "uh" as stand-alone fillers


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Um, which bank?", "Which bank?"),
        ("Oh, uh, I'm not sure.", "Oh, I'm not sure."),
        ("Well um I think so.", "Well I think so."),
        ("Which bank, um?", "Which bank?"),
        ("Hang on. Uh, say that again.", "Hang on. Say that again."),
    ],
)
def test_um_and_uh_are_removed(before: str, after: str) -> None:
    assert style_guard(before, call()) == after


@pytest.mark.parametrize("kept", ["Uh-huh, go on.", "Where's my umbrella?", "Huh? Which bank?"])
def test_words_that_only_contain_um_or_uh_are_kept(kept: str) -> None:
    assert style_guard(kept, call()) == kept


# ---- c. a last sentence that offers service is dropped


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Right, the bank. Do you need anything else?", "Right, the bank."),
        ("Oh, I see. What else do you need?", "Oh, I see."),
        ("A safe account? What should I do next?", "A safe account?"),
        ("Kestrel Bank. What details do you need from me?", "Kestrel Bank."),
        ("Hello? How can I help?", "Hello?"),
    ],
)
def test_last_sentence_offering_service_is_dropped(before: str, after: str) -> None:
    assert style_guard(before, call()) == after


def test_a_lone_service_sentence_is_kept_so_the_reply_is_never_empty() -> None:
    assert style_guard("How can I help?", call()) == "How can I help?"


# ---- d. a sentence offering her own details is dropped


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Oh my. Do you need my account number? Which bank?", "Oh my. Which bank?"),
        ("Shall I read you my card number? It's in my purse.", "It's in my purse."),
        ("Right. I can give you my sort code.", "Right."),
    ],
)
def test_sentence_offering_her_own_details_is_dropped(before: str, after: str) -> None:
    assert style_guard(before, call()) == after


def test_a_lone_offer_of_details_is_kept_so_the_reply_is_never_empty() -> None:
    lone = "Shall I read you my card number?"
    assert style_guard(lone, call()) == lone


def test_her_grandson_is_not_her_details() -> None:
    kept = "Do you want my grandson? He's out."
    assert style_guard(kept, call()) == kept


# ---- the guards inside tidy_reply: never empty, and the 200 character cut still holds


def test_a_reply_of_only_filler_is_never_emptied() -> None:
    assert style_guard("Um.", call()) == "Um."


def test_tidy_reply_runs_the_guards_and_still_cuts_to_the_limit() -> None:
    long = "Um, oh, I see. " + "The kettle is on and the post has come. " * 8
    out = tidy_reply(long, call("Go on, dear."))
    assert not out.lower().startswith("um")
    assert len(out) <= MAX_PERSONA_CHARS
    assert tidy_reply("Which bank, love?", call("Hello, love.")) == "Which bank?"


def test_safe_stall_is_never_changed_by_the_guards() -> None:
    # The stall says "love"; the guards run before the stall can be chosen, never on it
    out = tidy_reply("Read it to me: 4929 1234 5678 9012, love.", call("Hello, love."))
    assert out == SAFE_STALL


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Scones, flour and butter. Do you want the full list?", "Scones, flour and butter."),
        ("Oh, all sorts. Shall I list them?", "Oh, all sorts."),
        (
            "It's to do with the weather. Would you like me to explain?",
            "It's to do with the weather.",
        ),
    ],
)
def test_offers_to_list_or_explain_are_dropped(before: str, after: str) -> None:
    assert style_guard(before, call()) == after
