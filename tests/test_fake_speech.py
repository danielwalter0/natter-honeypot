from natter.providers.fakes import FakeSpeech


def test_fake_speech_returns_a_wav() -> None:
    data = FakeSpeech().speak("hello")
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"


def test_fake_speech_is_deterministic() -> None:
    speech = FakeSpeech()
    assert speech.speak("a") == speech.speak("b")


def test_fake_speech_records_texts() -> None:
    speech = FakeSpeech()
    speech.speak("one")
    speech.speak("two")
    assert speech.texts == ["one", "two"]
    assert speech.name == "fake-speech"
