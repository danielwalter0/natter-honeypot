import pytest

from natter.providers.errors import MissingKeyError, SpeechError
from natter.providers.groq_speech import GroqSpeech
from tests.fake_clients import FakeFactory


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(MissingKeyError, match="GROQ_API_KEY is not set"):
        GroqSpeech(client_factory=FakeFactory("groq-speech"))


def test_empty_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(MissingKeyError):
        GroqSpeech(client_factory=FakeFactory("groq-speech"))


def test_factory_gets_timeout_and_no_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    factory = FakeFactory("groq-speech")
    GroqSpeech(client_factory=factory)
    assert factory.factory_kwargs == {"api_key": "sk-test", "timeout": 30.0, "max_retries": 0}


def test_create_args_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    factory = FakeFactory("groq-speech")
    speech = GroqSpeech(client_factory=factory)
    data = speech.speak("[cheerful] hello")
    assert data[:4] == b"RIFF"
    # Exactly these arguments, and no sample_rate
    assert factory.create_calls == [
        {
            "model": "canopylabs/orpheus-v1-english",
            "voice": "diana",
            "input": "[cheerful] hello",
            "response_format": "wav",
        }
    ]
    assert speech.name == "groq:canopylabs/orpheus-v1-english:diana"


@pytest.mark.parametrize("bad", [b"", b"this is not a wav file"])
def test_bad_reply_raises(monkeypatch: pytest.MonkeyPatch, bad: bytes) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    speech = GroqSpeech(client_factory=FakeFactory("groq-speech", bad))
    with pytest.raises(SpeechError, match="not a WAV"):
        speech.speak("hello")


def test_over_200_characters_raises_without_a_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    factory = FakeFactory("groq-speech")
    with pytest.raises(SpeechError, match="over 200 characters"):
        GroqSpeech(client_factory=factory).speak("a" * 201)
    assert factory.create_calls == []


def test_exactly_200_characters_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    factory = FakeFactory("groq-speech")
    GroqSpeech(client_factory=factory).speak("a" * 200)
    assert len(factory.create_calls) == 1


@pytest.mark.parametrize("empty", ["", "   ", "\n\t"])
def test_empty_text_raises_without_a_call(monkeypatch: pytest.MonkeyPatch, empty: str) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "sk-test")
    factory = FakeFactory("groq-speech")
    with pytest.raises(SpeechError):
        GroqSpeech(client_factory=factory).speak(empty)
    assert factory.create_calls == []
