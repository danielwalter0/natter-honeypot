# 0001: The web page uses HTTP POST, not a WebSocket

Date: 2026-11-21. Status: accepted.

## Context

SPEC.md section 6 plans a WebSocket at `/ws/session` for the page. In practice each
step of a call is one request and one answer. In replay, "next turn" sends the next
script line. In live mode, the typed scammer line goes to `LiveCall.say` and one reply
comes back. Nothing is streamed: the reply text, the checked dossier and the audio
are all ready at the same moment.

## Decision

The page uses plain JSON over HTTP POST (`/api/step`, `/api/say`, `/api/reset`), served
by FastAPI on 127.0.0.1. Each answer is one "frame" that Python builds and the page
only draws.

## Why

- Shorter page code: one `fetch` per turn and no connection, reconnect or message-type
  handling. The owner does not write JavaScript, so less of it is better.
- Easier to secure and test: every request goes through the same Host and Origin
  allow-list check and a pydantic body model, and FastAPI's TestClient covers it
  with no socket.
- `LiveCall.say` blocks and holds a lock, which fits one request per turn. The page
  disables its input while a turn runs, so a double click cannot queue a second
  paid turn.

## Cost

- No server push. If streaming is added later (partial transcripts, mic input),
  a WebSocket comes back.
- A WebSocket would be checked once, at the handshake. Here the Host and Origin
  check runs on every request, so there is nothing to give up for that.
