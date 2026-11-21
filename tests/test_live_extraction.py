"""The owner's tests for LiveCall._run_extraction, reached through say()."""

from natter.live import LiveCall
from natter.providers.fakes import FakePersona, FakeSpeech
from natter.schema import Dossier, Evidence, Identifier, IdentifierKind, Turn

LINES = ["Call me on 07700 900482 now.", "Pay by bank transfer please.", "Hurry up."]
PHONE = Identifier(
    kind=IdentifierKind.PHONE,
    value="07700 900482",
    evidence=Evidence(turn=0, quote="07700 900482", confidence=0.9),
)
BAD = Identifier(
    kind=IdentifierKind.ALIAS,
    value="Nobody",
    evidence=Evidence(turn=0, quote="not in the turn", confidence=0.9),
)
FAKE_KEY = "sk-test-SECRET"


class ScriptedExtractor:
    """Counts calls, records what it saw, and fails on the calls listed in fail_on (1-based)."""

    name = "scripted"

    def __init__(self, dossiers: list[Dossier], fail_on: set[int] | None = None) -> None:
        self.dossiers = dossiers
        self.fail_on = fail_on or set()
        self.calls = 0
        self.seen: list[list[Turn]] = []

    def extract(self, transcript: list[Turn]) -> Dossier:
        self.calls += 1
        self.seen.append(transcript)
        if self.calls in self.fail_on:
            raise RuntimeError(FAKE_KEY)  # an SDK-style error holding a fake key
        return self.dossiers[min(self.calls - 1, len(self.dossiers) - 1)]


def make_call(extractor: ScriptedExtractor, max_extractions: int = 20) -> LiveCall:
    return LiveCall(FakePersona(), extractor, FakeSpeech(), max_extractions=max_extractions)


def test_failed_extraction_keeps_previous_dossier_and_reply_goes_on() -> None:
    good = Dossier(identifiers=[PHONE])
    call = make_call(ScriptedExtractor([good], fail_on={2}))
    first = call.say(LINES[0])
    second = call.say(LINES[1])
    assert second.dossier == first.dossier
    assert second.notes[0].startswith("extraction failed")
    assert second.text is not None  # the persona still replied
    assert call.say(LINES[2]).notes == []  # next say works


def test_extraction_note_never_holds_a_key() -> None:
    reply = make_call(ScriptedExtractor([Dossier()], fail_on={1})).say(LINES[0])
    assert FAKE_KEY not in " ".join(reply.notes)


def test_extractions_used_counts_failed_calls() -> None:
    call = make_call(ScriptedExtractor([Dossier()], fail_on={2}))
    for line in LINES:
        call.say(line)
    assert call.extractions_used == 3


def test_extraction_cap_stops_extractor_calls() -> None:
    extractor = ScriptedExtractor([Dossier(identifiers=[PHONE])])
    call = make_call(extractor, max_extractions=1)
    first = call.say(LINES[0])
    second = call.say(LINES[1])
    assert extractor.calls == 1
    assert second.notes == ["extraction cap reached"]
    assert second.dossier == first.dossier


def test_zero_extractions_never_calls_extractor() -> None:
    extractor = ScriptedExtractor([Dossier(identifiers=[PHONE])])
    reply = make_call(extractor, max_extractions=0).say(LINES[0])
    assert extractor.calls == 0
    assert reply.notes == ["extraction cap reached"]
    assert reply.dossier == Dossier()


def test_rejections_are_this_turns_drops_and_are_recorded() -> None:
    call = make_call(ScriptedExtractor([Dossier(identifiers=[BAD]), Dossier()]))
    first = call.say(LINES[0])
    second = call.say(LINES[1])
    assert len(first.rejections) == 1 and second.rejections == []
    assert call.state.rejections == first.rejections
    assert call.state.rejection_turns == [0]


def test_extractor_sees_snapshot_ending_with_new_scammer_turn() -> None:
    extractor = ScriptedExtractor([Dossier()])
    call = make_call(extractor)
    call.say(LINES[0])
    call.say(LINES[1])
    assert [t.text for t in extractor.seen[1]][-1] == LINES[1]
    assert extractor.seen[1][-1].speaker == "scammer"
    assert len(extractor.seen[1]) == 3  # scammer, persona, scammer
    assert extractor.seen[1] is not call.state.transcript  # a copy
