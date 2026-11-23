# AI use

This file says which AI tools I used to build Natter, what they did, and which models
run inside the product.

## What git history can and cannot show

Every commit on `main` is under my name because I ran nearly every git command and
opened and merged every pull request myself. Agents almost never committed or pushed,
partly to avoid mistakes such as leaking `.env`. The only exception was the slice that
switched the persona model: there I let the developer agent commit and push its branch,
and I amended the commit before merging. Claude Code adds a `Co-Authored-By` line by
default and I removed it where it appeared, so git history does not show agent work
and this file is the record.

## The spec, schema and project rules

I gave Claude the idea and the requirements. Claude drafted `docs/SPEC.md`,
`natter/schema.py`, `CLAUDE.md` and the agent definitions in `.claude/agents/`, and through
several rounds of feedback I approved them. 
They went in the first commit (`b4e61ea`, "Add spec, schema and agent
rules").

## Claude Code agents

I built the project in small slices with two Claude Code agents, both defined in
`.claude/agents/`.

- **developer** (`model: sonnet`): writes the code and tests for one approved slice.
  Its rules are to write a failing test first, keep files short and commented, and not
  to add dependencies, change `natter/schema.py`, change the provider interfaces or
  touch evaluation labels without stopping to ask. It runs lint and tests before it
  reports.
- **reviewer** (`model: opus`): reads a finished slice and tries to break it. It runs
  the tests but never edits files, and reports must fix, should fix and fine items with
  file names and line numbers.

`CLAUDE.md` sets the working rules for both: plan first and wait for my approval, test
first, keep every line explainable by me, and a list of security rules and things never
to do without asking. `.claude/settings.json` blocks agents from reading `.env` (added
in `46b8cbf`).

Some notes in `docs/known-limits.md` refer to reviewer work, for example "the reviewer
checked it by hand on fakes".

### Who wrote the code

I wrote the key logic of these parts myself. Claude gave me skeletons with blanks to fill in, 
and where my drafts had bugs it corrected them, in a few places by giving me the corrected code:

- the speech text preparation (`natter/speech_text.py`);
- the audio cache key (`natter/audio_key.py`);
- the session state functions (`natter/session.py`);
- the speech budget wrapper (`natter/speech_budget.py`);
- the live loop's extraction step (in `natter/live.py`);
- the goal reason sentences (`natter/goal_reason.py`);
- the fact row rendering in the page (`natter/web/app.js`).

Everything else in `natter/`, `tests/`, `scripts/` and the web page was written by the
developer agent. I used the reviewer agent on the riskier slices: speech, the live loop
and the reply guards.

## Claude as a planning guide

Outside the agents, I planned the work with Claude in a chat (Claude Sonnet 5.5). I used
it for the slice plans, for the prompts I gave the developer and reviewer agents, for
triage of the reviewer reports, and for plain-language explanations of the code, so that
I could explain every core line myself.

## What I did

- I wrote the message builder in the Groq persona (`build_messages` in
  `natter/providers/groq_persona.py`), which `docs/known-limits.md` calls "the owner's
  builder".
- I made the decisions to approve, change or reject each slice plan, and I made every
  merge.
- I ran the recording scripts (`scripts/record_cassettes.py`, `scripts/record_audio.py`
  and `scripts/record_filler.py`) with my own keys.
- I chose `openai/gpt-oss-120b` as the persona model, on Claude's advice, after comparing 
  outputs from `scripts/compare_persona.py`. The default moved from `openai/gpt-oss-20b` 
  to `openai/gpt-oss-120b` in `778ac39`.

The persona prompt wording was written by the developer agent, from findings I drew, 
with Claude's help, by reading and listening to real outputs. I judged the results.

## Evaluation scenarios and labels

The scammer scripts for the evaluation scenarios (`scenarios/*/script.json`) were
drafted by an agent. The labels (`scenarios/*/expected.json`) were drafted by Claude from
those scripts before any model answers were recorded. I then reviewed the scripts and
read the labels. I changed no label before seeing the results.

All scenarios are simulated. No real call, real person or real person's voice was used.

The evaluation write-up, `docs/evaluation.md`, was written by a Claude Code agent. I read
`docs/evaluation.md`.

## This README and this file

`README.md` and `ai.md` were drafted by Claude Code from the code as it stood on the
`eval-set` branch, with the commands run on Windows where possible. I have read, reviewed and edited these files.
The macOS and Linux commands follow the CI workflow and have not been run on those systems.

## Models inside the product

| Role | Model | Where |
|---|---|---|
| Extractor: reads the transcript and proposes the dossier | Claude, `claude-sonnet-5-5`, low effort, structured output | `natter/providers/claude_extractor.py` |
| Persona: writes her reply | Groq, `openai/gpt-oss-120b`, low reasoning effort, no tools | `natter/providers/groq_persona.py` |
| Speech: speaks her reply | Groq, `canopylabs/orpheus-v1-english`, voice `diana` | `natter/providers/groq_speech.py` |
| Voice input (live mode only) | the browser's speech recognition (Chrome or Edge) | `natter/web/app.js` |

In every case the model only proposes. Code checks each dossier quote against the
transcript and drops what fails, code chooses her goal, and fixed rules check her reply
before it is spoken (`natter/check.py`, `natter/picker.py`,
`natter/providers/reply_tidy.py`). The persona model has no tools and only a fake
identity.

The filler clips in `assets/filler/` and the replay audio in
`scenarios/bank-fraud-01/audio/` were made with the same Groq speech model and voice.
The recorded model answers in `scenarios/*/cache/` are real outputs from the extractor
and persona models, saved so that replay, the tests and the evaluation need no keys.
