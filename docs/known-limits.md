# Known limits

## Schema check

- The check proves a quote was said, not that it supports the value (e.g. "ank" can back "Barclays Bank"); the evaluation must catch this.
- Duplicate Turn.index values fail closed but can wrongly reject a good scammer quote; the session must keep indexes unique.
- check_dossier returns a shallow copy: the result shares objects with its input, so never mutate either in place.
- Rejections are returned, not logged; the caller (a later slice) must log them.
- Invisible characters (e.g. zero-width space) are not normalised, so "Mark from" does not match `"Ma\u200brk from"`.

## Session loop

- The extractor's dossier is not re-validated before check_dossier, so one built without validation (e.g. stage "bogus") is accepted and then crashes the next turn with KeyError.
- A scammer line or persona reply over 2000 characters (or a non-text reply) raises ValidationError and ends the run with no report; no truncate-or-end policy yet.
- The final dossier is the latest checked one, not merged across turns: a fact the extractor later forgets is lost (SPEC.md says the check "validates and merges"; undecided).

## Entry point (`__main__.py`)

- save_report trusts report.call_id for the file name; only the schema pattern protects it, so a Report built without validation could write outside reports/.
- build_report reads script.json twice and ignores each line's "turn" number, so a script whose numbering drifts would check expected.json evidence against the wrong turns.
- main() prints scammer text raw, so terminal escape sequences reach the terminal. The printed rejection count is mostly "cited turn does not exist" noise from the fake extractor, and rejections are not logged with their turn.
- call_id has one-second resolution, so two runs in the same second write the same file and the second overwrites the first.

## Cache

- Cache.load only checks the file parses; a wrong shape (list, number, null, `{}`), an empty/truncated/BOM file, or a mismatched stored provider/method raises an unhelpful error (TypeError/KeyError/JSONDecodeError), and in record mode a corrupt file is not re-recorded, it must be deleted by hand.
- Writes are not atomic: a crash mid-write leaves a truncated file. Reads and writes follow symlinks.
- The key has no prompt or model version, so after a prompt change replay serves stale replies; a real provider must put its version in `name`.

## Real providers

- Lookalike angle brackets (U+FF1C etc.) pass through the escaping. This is harmless as long as nothing NFKC-normalises the text.
- The persona 200-character limit is enforced only by the prompt and the token cap (the cache allows 2000); the hard check comes with the TTS slice.
- Provider errors end the whole session. SPEC asks for graceful degradation with a stall line and one retry (later slice).
- SDK exceptions carry the key in `exc.request.headers`, and `vars(client)` holds the key. Never log `exc.request`, or tracebacks with locals.
- Both SDKs honour `ANTHROPIC_BASE_URL` / `GROQ_BASE_URL` and `*_CUSTOM_HEADERS` env vars, so an env var can redirect the key. Consider an explicit `base_url`.
- `DOSSIER_SCHEMA` contains pattern/min/max keywords the structured-output API may reject. Check on the first record run.
- The cache key ignores prompt text, so re-record after any prompt change.
- No daily spend cap yet. A record run is bounded only by scenario length (about 20 calls, up to 2x with one retry).
- The `goal` argument is not type-checked in `build_messages` (only reachable from code; the owner's builder).
- Persona text in Groq assistant messages is not escaped (the owner's builder).
- The project venv is Python 3.14.5 while the project targets 3.12.
