# Natter

Natter is a honeypot voice agent. A chatty, confused "granny" persona answers
simulated scam calls, keeps the scammer talking, and builds an evidence-linked
dossier of the scam. The output is a JSON report. It is a local prototype for the
Hiya Voice AI Challenge and uses simulated scenarios only: no telephony, no real calls.

The design is in `docs/SPEC.md` and the report shape is in `natter/schema.py`.

## Setup (PowerShell)

```powershell
py -3.14 -m venv .venv            # or py -3.12 if you install it
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Commands

```powershell
python -m pytest                  # tests
ruff check .                      # lint
ruff format --check .             # formatting
mypy natter                       # types
python -m natter                  # run
```

The `make test`, `make lint` and `make run` targets wrap these same commands.
`make` is optional (for example `choco install make` on Windows).
