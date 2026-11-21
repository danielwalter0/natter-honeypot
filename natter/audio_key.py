from natter.cache import cache_key

SPEECH_METHOD = "speak:v1"


def speech_key(provider_name: str, prepared_text: str) -> str:
    """Cache file name for one spoken line. Bump v1 if the preparation rules change."""
    # return the result of cache_key with three things: the provider name,
    # SPEECH_METHOD, and a dict holding the prepared text under the key "text"
    return cache_key(provider_name, SPEECH_METHOD, {"text": prepared_text})
