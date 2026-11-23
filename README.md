# Natter

A honeypot voice agent that keeps phone scammers talking and writes down, with proof, everything they give away.

[![CI](https://github.com/danielwalter0/natter-honeypot/actions/workflows/ci.yml/badge.svg)](https://github.com/danielwalter0/natter-honeypot/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)

## What it is

Natter answers a simulated scam call as a chatty, confused older woman. While she
rambles and asks the caller to repeat things, an evidence dossier fills in: who they
claim to be, the callback number, the case reference, how they want to be paid and how
much. Every fact in the dossier carries a turn number, an exact quote from the caller
and a confidence. Code checks every quote against the transcript before the fact is
kept. Models propose, code decides. The result is a JSON report. It is a local
prototype built for the Hiya Voice AI Challenge, and it only ever talks to simulated
scammers: there is no telephony and no outbound calling.

![Natter replaying the recorded bank call: the call on the left, the evidence dossier on the right](docs/img/natter-page.png)

## Quick start (no API keys)

Replay mode plays a recorded call (`scenarios/bank-fraud-01`) from saved model answers
and saved audio. It needs no keys and makes no network calls. You need Python 3.12 or
newer (`requires-python = ">=3.12"` in `pyproject.toml`) and git.

**Windows (PowerShell)**

```powershell
python --version                  # check it says 3.12 or newer
git clone https://github.com/danielwalter0/natter-honeypot.git
cd natter-honeypot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m natter.web --replay
```

If you have several Pythons on Windows and `python` is older than 3.12, make the venv
with `py -3.12 -m venv .venv` instead.

If PowerShell says running scripts is disabled, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and activate again.

**macOS (zsh or bash)**

```bash
python --version                  # check it says 3.12 or newer
git clone https://github.com/danielwalter0/natter-honeypot.git
cd natter-honeypot
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m natter.web --replay
```

**Linux (bash or zsh)**

```bash
python --version                  # check it says 3.12 or newer
git clone https://github.com/danielwalter0/natter-honeypot.git
cd natter-honeypot
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m natter.web --replay
```

On macOS and Linux, if `python` is not found, use `python3` for the first and fourth
commands. Inside the active venv, `python` always works.

The server prints `Open http://127.0.0.1:8000 in a browser. Ctrl+C stops the server.`
Open that address and press **Next turn** to step through the call. Each step shows the
caller's line, her reply (with audio), the dossier so far and why she asked what she
asked. **Reset** starts the call again.

`python -m natter.web` with no flag is the same as `--replay`.

There is also a terminal version: `python -m natter --replay` plays the same call and
saves the report to `reports/<call id>.json`.

## Live mode

In live mode you play the scammer. You type (or say) a line, Claude extracts the
dossier, the persona replies through Groq and Groq speaks the reply.

It needs two environment variables. Natter reads them from the shell only; the app does
not read a `.env` file.

| Variable | Used by |
|---|---|
| `GROQ_API_KEY` | the persona (`openai/gpt-oss-120b`) and speech (`canopylabs/orpheus-v1-english`, voice `diana`) |
| `ANTHROPIC_API_KEY` | the extractor (`claude-sonnet-5-5`) |

Set them for the current shell, then start the server.

**PowerShell**

```powershell
$env:GROQ_API_KEY = "<your Groq key>"
$env:ANTHROPIC_API_KEY = "<your Anthropic key>"
python -m natter.web --live
```

**bash or zsh**

```bash
export GROQ_API_KEY="<your Groq key>"
export ANTHROPIC_API_KEY="<your Anthropic key>"
python -m natter.web --live
```

Add `--no-speech` (`python -m natter.web --live --no-speech`) for text replies only. No
speech request is ever made and no filler clips are loaded. `--no-speech` without
`--live` is an error.

Caps built into the code (`natter/live.py`, `natter/live_wiring.py`):

- each call stops at 40 turns (caller and persona together) or 600 seconds from its
  first line, and any line over 2000 characters is refused;
- at most 20 Claude extractions and 15 real speech requests per call;
- at least 7 seconds between speech requests, to stay under Groq's 10 requests a
  minute on the free tier;
- the Groq speech client never retries (`max_retries=0`), so one rate limit answer is
  one request, not three.

There is no daily spend cap yet. Restarting the server or pressing **Reset** starts a
fresh call with fresh caps, and `--live` prints a warning saying so at start.

Voice input uses the browser's own speech recognition, so it needs Chrome or Edge.
Other browsers hide the voice buttons and show "Voice input needs Chrome or Edge.";
the typed box still works. Use headphones: the microphone can pick up her reply from
your speakers. The microphone audio goes to the browser vendor's speech service, not to
Natter; only the recognised text reaches the server. Use simulated scam lines only.

## Troubleshooting

| What you see | Why, and what to do |
|---|---|
| `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)` on Windows, or `address already in use` on Linux and macOS | Something else is on port 8000, often a Natter server you already started. The port is fixed at 8000 (the Host and Origin allow-lists are built for it), so stop the other server and start again. |
| `GROQ_API_KEY is not set` or `ANTHROPIC_API_KEY is not set`, and the server exits | `--live` checks both keys before it starts. Set them in the same shell window (see Live mode). A `.env` file is not read. Replay needs no keys. |
| "Speech limit reached, showing text only." under a reply | Groq answered with a rate limit (HTTP 429). The reply still shows as text. Wait a minute, or use `--no-speech`. |
| "speech budget used up" under a reply | This call used its 15 speech requests. Press **Reset** for a new call. |
| "Could not play the audio." | The browser blocked or failed playback. Browsers only play sound after a click on the page, so click **Start call**, **Send** or a bubble's **Play** first. |
| "Voice input stopped (not-allowed). Type the line instead." | The microphone was blocked or is missing. Allow the microphone for `127.0.0.1` in the browser's site settings and press **Start call** again. The code in brackets is the browser's own error name. |
| "Could not reach the server." | The server stopped, or answered with something that is not JSON. Check the terminal it runs in. |
| The replay count is wrong after reloading the page | Reloading in the middle of a replay loses the page's place while the server carries on. Press **Reset**. |
| "Refused by server: a turn is already running" | One call per server. A second request while a turn runs is refused, not queued. Wait for the reply. |

## How it works

Each caller line is added to the transcript, then Claude reads the whole transcript as
delimited, escaped data and proposes a dossier. `check_dossier` then keeps only facts
whose quote really appears, after whitespace is normalised, in a turn the caller spoke,
and refuses a stage that moves backwards. Anything that fails is dropped and recorded
as a rejection. Code then picks the most valuable missing fact as her next goal
(callback number first, then payment method, organisation, case reference and amount),
never the same goal twice running. The persona model writes a short reply with that
goal and no tools. Fixed rules then tidy the reply and replace it with a safe stall line
if it would say a number the caller never said, sounds like a refusal or sounds like a
chatbot. Finally Groq speaks the reply, through a cache, a request budget and a
throttle. In replay mode the same steps run on recorded answers.

```mermaid
flowchart TD
    A[Scammer line] --> B[Claude extractor proposes a dossier]
    B --> C[check_dossier verifies quotes and stage]
    C -->|failed facts| R[Dropped and kept as rejections]
    C --> D[Code chooses the next goal]
    D --> E[Persona replies, Groq gpt-oss-120b]
    E --> F[Reply guards tidy or replace the reply]
    F --> G[Speech, Groq Orpheus]
    G --> H[Page shows reply, audio and dossier]
```

The full design is in [docs/SPEC.md](docs/SPEC.md) and the report shape is in
[natter/schema.py](natter/schema.py).

## Safety and design choices

- **Localhost only.** The server binds to `127.0.0.1:8000`, never `0.0.0.0`.
- **Host allow-list.** Every request must have Host `127.0.0.1:8000` or `localhost:8000`, which blocks DNS rebinding.
- **Origin allow-list.** Any request that changes state must carry the page's own Origin, and a GET from a foreign Origin is refused.
- **Content security policy.** Every response sends a strict CSP (`default-src 'self'`, no inline script, no framing) plus `nosniff`, `no-referrer` and `no-store`.
- **No API docs pages.** FastAPI's `/docs`, `/redoc` and `/openapi.json` are switched off.
- **No keys in logs.** Keys are read from the environment in one place per provider, a missing key error names the variable only, and SDK errors are shown by type and status only.
- **Errors never echo input.** A 500 says "server error" and a 422 names only known fields, so neither can repeat a key or the caller's text.
- **Scammer speech is data.** The transcript goes to Claude inside escaped `<transcript>` tags, with an instruction that its contents are untrusted.
- **Fail closed.** A fact whose quote is not in the cited caller turn is dropped.
- **Budget caps.** Per call limits on turns, time, extractions and speech requests, as listed under Live mode.
- **Replay first.** The default mode, the tests and the evaluation all run from recorded answers with no keys and no network, and replay can never make a paid call.
- **Microphone audio never reaches the server.** The browser turns speech into text, and only that text is sent.

## Evaluation

The evaluation replays every labelled scenario from its recorded answers and scores
the dossier against hand labels. It needs no keys and no network.

```bash
python scripts/evaluate.py                       # print the table, write spike_out/eval_table.md
python scripts/evaluate.py --details             # also list missed and extra items per scenario
python scripts/evaluate.py --transcript benign-01  # print one replayed call
```

The method, the scenarios and the results are in
[docs/evaluation.md](docs/evaluation.md). How labels are written is in
[scenarios/LABELS.md](scenarios/LABELS.md).

## Development

The same commands run in CI on Ubuntu (`.github/workflows/ci.yml`). Activate the venv
first.

**PowerShell**

```powershell
python -m pytest
ruff check .
ruff format --check .
mypy natter
```

**bash or zsh**

```bash
python -m pytest
ruff check .
ruff format --check .
mypy natter
```

The `Makefile` wraps these as `make test` and `make lint`, but `make` is optional.

Recording new cassettes or audio needs real keys and is done by the author only, with
`scripts/record_cassettes.py`, `scripts/record_audio.py` and `scripts/record_filler.py`.

## Project layout

```
natter/
  web/                 the page server (server.py) and the page (index.html, app.js, style.css)
  live.py              LiveCall: one caller line in, one reply out, with the per call caps
  live_wiring.py       builds a live call: real providers plus cache, budget and throttle
  web_wiring.py        builds a replay call from recorded answers
  session.py           the turn steps shared by replay and live
  check.py             check_dossier: the quote and stage check
  picker.py            chooses the next goal
  schema.py            the report and dossier shape (Pydantic)
  cache.py             record and replay of model answers
  audio_cache.py       record and replay of speech WAVs
  speech_budget.py     hard cap on real speech requests
  throttle.py          minimum gap between speech requests
  evaluate.py, scoring.py, labels.py  evaluation scoring
  providers/           Claude extractor, Groq persona, Groq speech, fakes, reply guards
scenarios/<name>/      script.json (caller lines), expected.json (labels), cache/ and audio/
assets/filler/         short filler clips played while a live reply is made
scripts/               evaluation, recording and persona comparison scripts
tests/                 pytest suite
docs/                  SPEC.md, known-limits.md, evaluation.md, decisions/
```

## Limits

Everything we know is missing or weak is listed in
[docs/known-limits.md](docs/known-limits.md).

## AI use

How AI tools were used to build Natter, and which models run inside it, is in
[ai.md](ai.md).

