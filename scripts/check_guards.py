"""Read-only check: would today's reply guards change any recorded persona reply?

For each scenario, replay the cassettes (no keys, no network, nothing is written), then
run tidy_reply over every persona reply with the transcript before it, and print any
reply that comes out different. Rerun after changing natter/providers/reply_tidy.py.
"""

import sys

from natter.__main__ import ROOT
from natter.cache import CacheMiss
from natter.evaluate import replay_session
from natter.providers.reply_tidy import SAFE_STALL, tidy_reply

SCENARIOS = ["bank-fraud-01", "hmrc-arrest-01", "tech-support-01", "benign-01", "injection-01"]


def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    for name in SCENARIOS:
        try:
            transcript = replay_session(ROOT / "scenarios" / name).transcript
        except CacheMiss:
            print(f"{name}: not recorded")
            continue
        checked, skipped, changed = 0, 0, []
        for i, turn in enumerate(transcript):
            if turn.speaker != "persona":
                continue
            if turn.text == SAFE_STALL:  # already a stall: tidy only re-words it, not a real change
                skipped += 1
                continue
            checked += 1
            after = tidy_reply(turn.text, transcript[:i])  # only turns before this reply
            if after != turn.text:
                changed.append((turn.index, turn.text, after))
        print(
            f"{name}: replies checked {checked}, changed {len(changed)}, skipped {skipped} stalls"
        )
        for index, before, after in changed:
            print(f"  [{index}] {before!r} -> {after!r}")


if __name__ == "__main__":
    main()
