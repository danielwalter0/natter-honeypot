"""Score every labelled scenario in replay mode and write spike_out/eval_table.md.

No keys and no network: it only reads the recorded cassettes.
  --details          also print missed/extra items and rejections per scored scenario
  --transcript NAME  print only that scenario's replayed call (no table, no labels needed)
"""

import argparse
import sys

from natter.__main__ import ROOT
from natter.cache import CacheMiss
from natter.eval_details import details_text, transcript_lines
from natter.eval_table import render_table
from natter.evaluate import replay_all, replay_session, row_for, valid_scenario_name

NEWLINE = "\n"


def main() -> None:
    # Same console safety as natter/__main__.py
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Replay and score the scenarios")
    parser.add_argument("--details", action="store_true", help="print missed/extra and rejections")
    parser.add_argument("--transcript", metavar="NAME", help="print one replayed call and stop")
    args = parser.parse_args()

    if args.transcript is not None:
        folder = ROOT / "scenarios" / args.transcript
        if not valid_scenario_name(args.transcript) or not (folder / "script.json").is_file():
            parser.error(f"no scenario {args.transcript!r} with a script.json")
        try:
            result = replay_session(folder)
        except CacheMiss:
            sys.exit(f"{args.transcript}: not recorded (no cassette for this call)")
        print(NEWLINE.join(transcript_lines(result.transcript)))
        return

    outcomes = replay_all(ROOT / "scenarios")
    table = render_table([row_for(o) for o in outcomes])
    out = ROOT / "spike_out" / "eval_table.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(table + NEWLINE, encoding="utf-8")  # the file never holds the details
    print(table)
    if args.details:
        for o in outcomes:
            if o.result is not None:  # only scored scenarios
                print()
                print(
                    details_text(
                        o.name,
                        o.raw,
                        o.result.dossier,
                        o.result.rejections,
                        o.result.rejection_turns,
                    )
                )


if __name__ == "__main__":
    main()
