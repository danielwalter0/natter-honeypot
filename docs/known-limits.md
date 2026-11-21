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

## Live loop (`live.py`)

- The time cap is checked only when a line arrives. A `say()` that starts just under 600 s can still run an extraction (up to about 60 s worst case: 30 s timeout x 2 tries), the persona and the 7 s speech throttle, so a call can end around 670 s.
- "`say()` never raises" covers `Exception` only. A `BaseException` such as `KeyboardInterrupt` in the middle of a turn leaves a scammer turn with no reply.
- No daily speech or spend cap yet (`NATTER_DAILY_SPEND_CAP_USD` is not built). Every new `LiveCall` gets a fresh 15 speech requests and 20 extractions.
- With an odd turn cap the last scammer line still costs one paid extraction but gets no reply (same as `run_session`).
- `LiveCall` strips leading and trailing spaces from each line and `run_session` does not, so the two transcripts differ for padded lines.
- The lock around `say()` is untested (removing it passes every test).
- If the live audio folder (`live_cache/audio`) reaches `AudioCache`'s 8 MB cap, the real speech request is still made (and counts against the quota), then `store` raises "audio folder is full". The reply loses its audio and carries a "speech failed" note. Each later new line does the same, so delete old WAVs from `live_cache/audio` to carry on.
- The live audio is never played or saved by the terminal loop (`live_cli.py`); only its size is printed. WAVs exist only in the speech cache under `live_cache/`.
- A scammer line that is the literal text `quit` ends the terminal loop instead of being sent.
- `python -m natter.live` runs `live.py` as `__main__` and imports `live_cli`, which imports `natter.live` again as a normal module, so the module is loaded twice. This is harmless (the loop uses the second copy) but would surprise anyone adding module-level state to `live.py`.

## Web page (`natter/web/`, slice 7)

- No daily spend cap (`NATTER_DAILY_SPEND_CAP_USD` is not built). `python -m natter.web --live` prints a warning at start. Each server start, and each reset, gets a fresh `LiveCall` with its own per-call caps (40 turns, 20 extractions, 15 speech requests, 600 s), so restarting the server resets the spend limits.
- One call per server process: two browser tabs share and drive the same call. A turn, a step and a reset share one lock; a second request while one runs gets 409, it is not queued.
- Request bodies have no overall size cap (SPEC says 64 KB). `line` is limited to 2000 characters, but FastAPI reads and parses the whole body first. Local only, so low risk; a Content-Length check is a later fix.
- Reloading the page in the middle of a replay loses its place: the page shows "0 of 10" with no bubbles, while the server carries on from where it was, so the next click plays a later line. Press Reset after a reload. (After the end, a reload is handled: the "replay finished" answer switches Next turn off.)
- If the server answers with something that is not JSON (an HTML error page from a proxy, a 502), the page says "Could not reach the server." A JSON error with no `detail` shows "Refused by server: undefined". Both are misleading but safe.
- Audio uses one shared player: a new Play stops and rewinds the current clip, and a failed `play()` shows "Could not play the audio." The reason it failed is not shown.
- If `/api/step` fails with a 500 after the server has used up the line, the page's "N of 10 lines" count is one behind the server.
- If the first `/api/mode` request fails, the page never learns its mode; a later Reset shows "replay" and hides both control sets. Reload the page.
- The CSP allows `media-src data:` for the reply audio. Only Python builds those URLs (a fixed prefix plus base64), so no untrusted text reaches them; `blob:` would be tighter.
- uvicorn's access log includes query strings (`POST /api/step?x=...`). The page never sends any and bodies are not logged, so only someone typing a URL by hand can put text there.
- `goal_reason`'s last branch ("No question this reply.") cannot be reached with `choose_goal` as written; it is kept as a safe default.
- `build_frame` spots a stall, a failed extraction and a hit extraction cap by matching the start of `LiveCall`'s notes ("persona failed", "extraction failed", "extraction cap"). Rewording those notes in `live.py` breaks this silently in code, though the web_view tests would fail.
- Test gaps: the replay parity test does not compare rejections or rejection turns (the recorded call has none), and no `build_frame` test runs the "does not repeat herself" goal branch end to end (the reviewer checked it by hand on fakes).
- The call's 600 s clock starts at its first line, not when the call is built, so a server left idle keeps the full time. Reset builds a new call, whose clock starts at its own first line.

## Voice input (`app.js`, live mode)

- Chrome and Edge only (the browser's `webkitSpeechRecognition`). Other browsers hide the voice buttons and show "Voice input needs Chrome or Edge."; the typed box still works.
- The microphone audio goes to the browser vendor's speech service (Google for Chrome, Microsoft for Edge), not to Natter. Only the recognised text reaches our server. Use simulated scam lines only, never a real person's voice.
- Listening is paused while a turn runs and while the reply plays, but the microphone still picks up speaker output, for example a Play click on an old bubble during a call, or the tail of a clip. Use headphones.
- Recognition errors: silence (`no-speech`) just listens again. Any other error (microphone blocked, no network, no microphone) ends the voice call with a status line naming the browser's error code; press Start call again or type the line.
- Recognition mistakes are sent as heard. A misheard line is a real scammer turn: it costs an extraction and is in the transcript. There is no "check before sending" step.
- Each final result is one turn, so a long sentence with a pause in it can arrive as two turns.
- Audio plays on its own only after the Start call click (the browser's sound rule). If `play()` still fails, the page says "Could not play the audio." and listens again straight away.
- The voice code is not browser-tested: the tests are text checks on `app.js` and `index.html`. `app.js` is now well over the 200-line guide.
