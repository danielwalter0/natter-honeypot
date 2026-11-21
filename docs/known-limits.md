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
- An `account_number` identifier's value can carry both the sort code and the account number in one string.
- check_dossier normalises whitespace only, not Unicode hyphens or curly quotes, so a quote must use exactly the character the turn uses (U+2011 vs "-") or the fact is dropped.
- A fake `[1] persona:` label inside a single scammer line is possible (newlines are collapsed, so it cannot start a line). It fails safe: the evidence check uses the real turn.
- Nothing in code catches an injection the extractor itself fails to flag as `injection_attempt`.

## Entry point (`__main__.py`)

- save_report trusts report.call_id for the file name; only the schema pattern protects it, so a Report built without validation could write outside reports/.
- build_report reads script.json twice and ignores each line's "turn" number, so a script whose numbering drifts would check expected.json evidence against the wrong turns.
- main() prints scammer text raw, so terminal escape sequences reach the terminal. In the no-flag run the printed rejection count is mostly "cited turn does not exist" noise from the fake extractor, and only the count is printed; `--replay` prints each rejection with its turn.
- call_id has one-second resolution, so two runs in the same second write the same file and the second overwrites the first.

## Cache

- Cache.load only checks the file parses; a wrong shape (list, number, null, `{}`), an empty/truncated/BOM file, or a mismatched stored provider/method raises an unhelpful error (TypeError/KeyError/JSONDecodeError), and in record mode a corrupt file is not re-recorded, it must be deleted by hand.
- Writes are not atomic: a crash mid-write leaves a truncated file. Reads and writes follow symlinks.
- The key has no prompt or model version, so after a prompt change replay serves stale replies; a real provider must put its version in `name`.
- Replay trusts cassettes more than the live path: replayed persona replies are not re-tidied (only `checked_reply`, up to 2000 characters), and replayed dossiers are validated without strict mode (`"turn": "0"` is accepted). Only our own recorder writes cassettes.

## Real providers

- Lookalike angle brackets (U+FF1C etc.) pass through the escaping. This is harmless as long as nothing NFKC-normalises the text.
- Live persona replies are cut to 200 characters by `cut_to_limit` in `reply_tidy.py`; replayed replies are not (see Cache).
- Provider errors end the whole session, and one failed extraction ends the whole call with nothing saved. SPEC asks for graceful degradation with a stall line and one retry (later slice).
- An empty or over-long Groq reply raises `ValueError` (from `checked_reply`), not `PersonaError`.
- SDK exceptions carry the key in `exc.request.headers`, and the real SDK client holds the key internally (`vars(client)`). Never log `exc.request`, or tracebacks with locals.
- Both SDKs honour `ANTHROPIC_BASE_URL` / `GROQ_BASE_URL` and `*_CUSTOM_HEADERS` env vars, so an env var can redirect the key. Consider an explicit `base_url`.
- `DOSSIER_SCHEMA` is sent through `sanitise_schema`, which strips the min/max/length keywords the structured-output API rejects; only the simple currency `pattern` remains, and the recorded run was accepted. The stripped limits are stated in the prompt and enforced by strict `parse_reply`.
- The cache key ignores prompt text, so prompt changes need a re-record.
- No daily spend cap yet. A record run is bounded only by scenario length (about 20 calls, up to 2x with one retry).
- The `goal` argument is not type-checked in `build_messages` (only reachable from code; the owner's builder).
- Persona text in Groq assistant messages is not escaped (the owner's builder).
- The project venv is Python 3.14.5 while the project targets 3.12.
- Prompt wording cannot be unit-tested, so the re-recorded cassettes are the check.
- Words glued in the middle ("giveme") cannot be repaired by rules, so the cassettes must be read by eye.

## Reply tidy (`reply_tidy.py`)

- Numbers written as words ("one two three four") and numbers of 3 digits or fewer pass the number guard. A plausible year such as "1952" becomes a stall (fails safe), as do separate small numbers joined by punctuation ("12, 34").
- The refusal guard only matches known openers at the start of a reply; other refusals pass. An in-character reply that starts like one ("I can't help it, dear") becomes a stall (fails safe).
- The seam rule cuts abbreviations ("Mr.Smith" becomes "Mr.", "the U.K." becomes "the U.") and misses `"dear\u2026Could"`, because the ellipsis is mapped to "..." only after the seam check.
- `NATTER_RAW_LOG` is debug-only. It writes raw model text to any path it is given (point it into `spike_out/`, which is gitignored), and a bad path raises `OSError` and ends the call.

## Speech (`audio_cache.py`, `groq_speech.py`, `throttle.py`)

- `is_wav` checks only the RIFF/WAVE marks. Groq streams WAVs with a placeholder data length (Python's `wave` reads about 89,000 s), so neither the duration nor the length fields are checked. Only the 1 MB per-file and 8 MB per-folder caps bound the audio.
- If a store fails after the `.wav.tmp` write and before `os.replace`, the `.tmp` file is left behind. It is never loaded, but it must not be committed.
- The audio key covers the prepared text and the provider name (model and voice), plus a `speak:v1` method version. If the prep rules or the direction tag change and the version is not bumped, replay serves stale WAVs.
- If the text cassettes are re-recorded, every audio key goes stale. Replay then raises `CacheMiss` and never calls Groq, but all the audio must be re-recorded, which costs free-tier quota.
- Committed WAVs stay in git history for good, so every re-record adds about 5 MB to the clone.
- The throttle limits requests per minute only. It does not track Groq's per-minute or per-day token caps. A 429 ends the record run (`max_retries=0`), and a rerun resumes from the cache.
- `record_audio.py` replays the text cassettes to find the persona lines, so audio can only be made for a scenario that already has text cassettes.
- The pre-flight cap is 12 real requests per run.
- Errors from our own code (ValueError, SpeechError, MissingKeyError, CacheMiss) show their message. SDK errors are reported by type and status only, so the Groq error message is not shown. The owner reads it in the Groq console.
- The recorder treats a truncated or non-WAV file as missing and re-records it, overwriting the bad file.
- No 15 s per-clip duration check (SPEC.md asks for 15 s and 1 MB per turn). The owner accepted this: at 24 kHz mono 16-bit, 1 MB is about 21 s, and the 1 MB cap bounds it in practice.
