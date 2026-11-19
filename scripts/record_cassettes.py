"""Record real Groq and Claude answers for bank-fraud-01 into the cache folder.

Run by the owner only, with GROQ_API_KEY and ANTHROPIC_API_KEY set in the shell.
Prints the turn count and rejection count, never a key.
"""

from natter.__main__ import MAX_TURNS, SCENARIO, load_lines
from natter.cache import Cache, CachedExtractor, CachedPersona
from natter.providers.claude_extractor import ClaudeExtractor
from natter.providers.groq_persona import GroqPersona
from natter.session import run_session

CASSETTES = SCENARIO / "cache"


def main() -> None:
    cache = Cache(CASSETTES, "record")
    persona = CachedPersona(GroqPersona(), cache)
    extractor = CachedExtractor(ClaudeExtractor(), cache)
    result = run_session(load_lines(SCENARIO), persona, extractor, MAX_TURNS)
    print(f"Turns: {len(result.transcript)}")
    print(f"Rejections: {len(result.rejections)}")


if __name__ == "__main__":
    main()
