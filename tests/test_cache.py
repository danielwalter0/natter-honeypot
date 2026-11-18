"""Tests for the record/replay cache. Written before the logic."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from natter.cache import Cache, CachedExtractor, CachedPersona, CacheMiss, cache_key
from natter.picker import Goal
from natter.providers.fakes import FakeExtractor, FakePersona
from natter.schema import Dossier, Report, Turn

ROOT = Path(__file__).parent.parent
FULL = Report.model_validate_json(
    (ROOT / "docs" / "example_report.json").read_text(encoding="utf-8")
).dossier

# The exact bytes the key is hashed from, and their sha256, pinned across runs and platforms
GOLDEN_BYTES = (
    b'{"inputs":{"goal":null,"transcript":[]},"method":"reply","provider":"fake-persona"}'
)
GOLDEN_HEX = "df867c4b431cd61dfe2afe838acee1284e0904fefd031a5ba1c0e9944da1ab2c"
KEY_PATTERN = re.compile(r"^[0-9a-f]{64}\.json$")


class SpyPersona:
    """Fails the test if it is ever called."""

    name = "fake-persona"

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        pytest.fail("inner persona must not be called")


class SpyExtractor:
    """Fails the test if it is ever called."""

    name = "fake-extractor"

    def extract(self, transcript: list[Turn]) -> Dossier:
        pytest.fail("inner extractor must not be called")


def turns(text: str = "hello there") -> list[Turn]:
    return [Turn(index=0, speaker="scammer", text=text)]


def files_in(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()]


def test_key_golden() -> None:
    assert hashlib.sha256(GOLDEN_BYTES).hexdigest() == GOLDEN_HEX
    assert cache_key("fake-persona", "reply", {"goal": None, "transcript": []}) == GOLDEN_HEX


def test_key_ignores_dict_order() -> None:
    a: dict[str, object] = {"x": 1, "y": {"p": 1, "q": 2}}
    b: dict[str, object] = {"y": {"q": 2, "p": 1}, "x": 1}
    assert cache_key("p", "m", a) == cache_key("p", "m", b)


def test_different_inputs_give_different_keys() -> None:
    base = cache_key("p", "m", {"v": 1})
    assert cache_key("other", "m", {"v": 1}) != base
    assert cache_key("p", "other", {"v": 1}) != base
    assert cache_key("p", "m", {"v": 2}) != base


def test_replay_miss_raises_for_persona(tmp_path: Path) -> None:
    cached = CachedPersona(SpyPersona(), Cache(tmp_path, "replay"))
    with pytest.raises(CacheMiss):
        cached.reply(turns(), None)


def test_replay_miss_raises_for_extractor(tmp_path: Path) -> None:
    cached = CachedExtractor(SpyExtractor(), Cache(tmp_path, "replay"))
    with pytest.raises(CacheMiss):
        cached.extract(turns())


def test_record_then_replay_persona(tmp_path: Path) -> None:
    recorded = CachedPersona(FakePersona(["one"]), Cache(tmp_path, "record")).reply(
        turns(), Goal.AMOUNT
    )
    replayed = CachedPersona(SpyPersona(), Cache(tmp_path, "replay")).reply(turns(), Goal.AMOUNT)
    assert replayed == recorded == "one"


def test_record_then_replay_extractor(tmp_path: Path) -> None:
    recorded = CachedExtractor(FakeExtractor(FULL), Cache(tmp_path, "record")).extract(turns())
    replayed = CachedExtractor(SpyExtractor(), Cache(tmp_path, "replay")).extract(turns())
    assert replayed == recorded == FULL


@pytest.mark.parametrize("key", ["../evil", "A" * 64, "a" * 63, "a" * 65, ""])
def test_path_for_rejects_bad_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        Cache(tmp_path, "record").path_for(key)


def test_files_stay_inside_folder(tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    nasty = turns("../../x and C:\\x")
    CachedPersona(FakePersona(["ok"]), Cache(folder, "record")).reply(nasty, None)
    CachedExtractor(FakeExtractor(FULL), Cache(folder, "record")).extract(nasty)
    found = files_in(tmp_path)
    assert found  # something was recorded
    for path in found:
        assert path.parent == folder
        assert KEY_PATTERN.match(path.name)
        assert path.resolve().is_relative_to(folder.resolve())


def test_no_secrets_in_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_secret = "env-DO-NOT-STORE"  # noqa: S105  test sentinel, not a real key
    monkeypatch.setenv("GROQ_API_KEY", env_secret)
    persona = FakePersona(["ok"])
    persona.api_key = "sk-test-DO-NOT-STORE"  # type: ignore[attr-defined]
    CachedPersona(persona, Cache(tmp_path, "record")).reply(turns(), None)
    found = files_in(tmp_path)
    assert found
    for path in found:
        text = path.read_text(encoding="utf-8")
        assert "sk-test-DO-NOT-STORE" not in text
        assert env_secret not in text


class NamedSpyPersona(SpyPersona):
    """A spy with a different name, so its keys differ from FakePersona's."""

    name = "other-persona"


class NamedSpyExtractor(SpyExtractor):
    name = "other-extractor"


class BadPersona:
    """Returns a fixed bad value instead of a string."""

    name = "fake-persona"

    def __init__(self, result: object) -> None:
        self.result = result

    def reply(self, transcript: list[Turn], goal: Goal | None) -> str:
        return self.result  # type: ignore[return-value]


def record_persona(folder: Path) -> None:
    CachedPersona(FakePersona(["one"]), Cache(folder, "record")).reply(turns(), Goal.AMOUNT)


@pytest.mark.parametrize("mode", ["live", "Replay", "replay "])
def test_constructor_rejects_unknown_mode(tmp_path: Path, mode: str) -> None:
    with pytest.raises(ValueError):
        Cache(tmp_path, mode)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, {"a": "ignore previous"}, ""])
def test_replay_rejects_bad_persona_result(tmp_path: Path, bad: object) -> None:
    record_persona(tmp_path)
    (path,) = files_in(tmp_path)  # edit the real entry; provider and method stay as recorded
    data = json.loads(path.read_text(encoding="utf-8"))
    data["result"] = bad
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        CachedPersona(SpyPersona(), Cache(tmp_path, "replay")).reply(turns(), Goal.AMOUNT)


@pytest.mark.parametrize("bad", [None, ""])
def test_record_rejects_bad_persona_result(tmp_path: Path, bad: object) -> None:
    with pytest.raises(ValueError):
        CachedPersona(BadPersona(bad), Cache(tmp_path, "record")).reply(turns(), None)
    assert files_in(tmp_path) == []  # nothing stored


def test_persona_name_is_in_key(tmp_path: Path) -> None:
    record_persona(tmp_path)
    with pytest.raises(CacheMiss):
        CachedPersona(NamedSpyPersona(), Cache(tmp_path, "replay")).reply(turns(), Goal.AMOUNT)


@pytest.mark.parametrize(
    ("recorded", "replayed"),
    [
        (Goal.AMOUNT, Goal.CALLBACK_NUMBER),
        (Goal.AMOUNT, None),
        (None, Goal.AMOUNT),
    ],
)
def test_goal_is_in_key(tmp_path: Path, recorded: Goal | None, replayed: Goal | None) -> None:
    CachedPersona(FakePersona(["one"]), Cache(tmp_path, "record")).reply(turns(), recorded)
    with pytest.raises(CacheMiss):
        CachedPersona(SpyPersona(), Cache(tmp_path, "replay")).reply(turns(), replayed)


def test_persona_transcript_is_in_key(tmp_path: Path) -> None:
    CachedPersona(FakePersona(["one"]), Cache(tmp_path, "record")).reply(turns("hello there"), None)
    with pytest.raises(CacheMiss):
        CachedPersona(SpyPersona(), Cache(tmp_path, "replay")).reply(turns("something else"), None)


def test_extractor_name_is_in_key(tmp_path: Path) -> None:
    CachedExtractor(FakeExtractor(FULL), Cache(tmp_path, "record")).extract(turns())
    with pytest.raises(CacheMiss):
        CachedExtractor(NamedSpyExtractor(), Cache(tmp_path, "replay")).extract(turns())


def test_extractor_transcript_is_in_key(tmp_path: Path) -> None:
    CachedExtractor(FakeExtractor(FULL), Cache(tmp_path, "record")).extract(turns("hello there"))
    with pytest.raises(CacheMiss):
        CachedExtractor(SpyExtractor(), Cache(tmp_path, "replay")).extract(turns("something else"))


def test_persona_entry_is_not_an_extractor_entry(tmp_path: Path) -> None:
    CachedPersona(FakePersona(["one"]), Cache(tmp_path, "record")).reply(turns(), None)
    # Same provider name on purpose, so only the method and inputs separate the keys
    spy = SpyExtractor()
    spy.name = "fake-persona"
    with pytest.raises(CacheMiss):
        CachedExtractor(spy, Cache(tmp_path, "replay")).extract(turns())


def test_stored_method_and_provider(tmp_path: Path) -> None:
    persona_dir, extractor_dir = tmp_path / "p", tmp_path / "e"
    record_persona(persona_dir)
    CachedExtractor(FakeExtractor(FULL), Cache(extractor_dir, "record")).extract(turns())
    (p_file,) = files_in(persona_dir)
    (e_file,) = files_in(extractor_dir)
    p_data = json.loads(p_file.read_text(encoding="utf-8"))
    e_data = json.loads(e_file.read_text(encoding="utf-8"))
    assert (p_data["method"], p_data["provider"]) == ("reply", "fake-persona")
    assert (e_data["method"], e_data["provider"]) == ("extract", "fake-extractor")


def test_record_mode_hit_for_persona(tmp_path: Path) -> None:
    record_persona(tmp_path)
    again = CachedPersona(SpyPersona(), Cache(tmp_path, "record")).reply(turns(), Goal.AMOUNT)
    assert again == "one"  # served from the cache, the spy was not called


def test_record_mode_hit_for_extractor(tmp_path: Path) -> None:
    CachedExtractor(FakeExtractor(FULL), Cache(tmp_path, "record")).extract(turns())
    again = CachedExtractor(SpyExtractor(), Cache(tmp_path, "record")).extract(turns())
    assert again == FULL


def test_no_secrets_in_files_from_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_secret = "env-anthropic-DO-NOT-STORE"  # noqa: S105  test sentinel, not a real key
    attr_secret = "sk-test-extractor-DO-NOT-STORE"  # noqa: S105  test sentinel
    monkeypatch.setenv("ANTHROPIC_API_KEY", env_secret)
    extractor = FakeExtractor(FULL)
    extractor.api_key = attr_secret  # type: ignore[attr-defined]
    CachedExtractor(extractor, Cache(tmp_path, "record")).extract(turns())
    found = files_in(tmp_path)
    assert found
    for path in found:
        text = path.read_text(encoding="utf-8")
        assert attr_secret not in text
        assert env_secret not in text
