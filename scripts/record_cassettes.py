"""Record real Groq and Claude answers for one scenario into its cache folder (text only).

Run by the owner only, with GROQ_API_KEY and ANTHROPIC_API_KEY set in the shell.
Usage: python scripts/record_cassettes.py [--scenario NAME]   (default bank-fraud-01)
Prints the turn count and rejection count, never a key.
"""

import argparse

from natter.__main__ import MAX_TURNS, ROOT, load_lines
from natter.cache import Cache, CachedExtractor, CachedPersona
from natter.evaluate import valid_scenario_name
from natter.providers.claude_extractor import ClaudeExtractor
from natter.providers.groq_persona import GroqPersona
from natter.session import run_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Record text cassettes for one scenario")
    parser.add_argument("--scenario", default="bank-fraud-01", help="folder name under scenarios/")
    args = parser.parse_args()
    if not valid_scenario_name(args.scenario):
        parser.error("scenario name must match [a-z0-9_-]{1,64}")
    folder = ROOT / "scenarios" / args.scenario
    if not (folder / "script.json").is_file():
        parser.error(f"no script.json in scenarios/{args.scenario}")
    cache = Cache(folder / "cache", "record")
    persona = CachedPersona(GroqPersona(), cache)
    extractor = CachedExtractor(ClaudeExtractor(), cache)
    result = run_session(load_lines(folder), persona, extractor, MAX_TURNS)
    print(f"Turns: {len(result.transcript)}")
    print(f"Rejections: {len(result.rejections)}")


if __name__ == "__main__":
    main()
