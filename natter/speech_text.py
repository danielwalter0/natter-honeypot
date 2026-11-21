import re

MAX_SPEECH_CHARS = 200
DIRECTION = "[warm]"


def prepare_speech_text(text: str, direction: str) -> str:
    """Return the exact text we send to the voice. Same input, same output, always."""
    # 1. remove [anything in square brackets]
    text = re.sub(r"\[[^\]]*\]", "", text)
    # 1b. remove any leftover single bracket, such as an unclosed "[warm"
    text = re.sub(r"[\[\]]", "", text)

    # 2. collapse runs of spaces and strip the ends
    clean_text = " ".join(text.split())

    # 3. nothing left? refuse
    if not clean_text:
        raise ValueError("nothing to say")

    # 4. tagged version
    tagged = direction + " " + clean_text

    # 5. tag fits? use it
    if len(tagged) <= MAX_SPEECH_CHARS:
        return tagged

    # 6. tag does not fit, but the clean text does? send it with no tag
    if len(clean_text) <= MAX_SPEECH_CHARS:
        return clean_text

    # 7. too long either way
    raise ValueError("text too long")
