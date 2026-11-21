"""The local web server for the Natter page. Local only; no static routes yet.

Design
- FastAPI(docs_url=None, redoc_url=None, openapi_url=None): no /docs, no schema.
- A small dataclass CallHolder(call, lines, next_line, lock: threading.Lock) lives
  on app.state.holder.
- An http middleware runs on EVERY request:
  - Host must be exactly 127.0.0.1:{port} or localhost:{port}, else 403
    {"detail": "forbidden"}. This is the DNS-rebinding defence.
  - Any request that is not GET or HEAD must carry an Origin equal to
    http://127.0.0.1:{port} or http://localhost:{port}, else 403.
  - A GET that carries a foreign Origin is also 403.
  - Security headers go on every response, including 403s: Content-Security-Policy
    "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' data:;
    connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none';
    frame-ancestors 'none'; form-action 'none'", X-Content-Type-Options nosniff,
    Referrer-Policy no-referrer, X-Frame-Options DENY, Cache-Control no-store.
- GET /api/mode -> {"mode", "speech_cap", "lines_total" (len(lines) or None)}.
- POST /api/step (replay only; live gives 404 {"detail": "not found"}):
  - lines used up -> 409 {"detail": "replay finished"}.
  - else record turns_before and previous_goal from call.state, call.say(next line),
    then build_frame(...). On the LAST line the returned frame has ended=True
    (model_copy(update=...)).
- POST /api/say (live only; replay gives 404). Body model SayBody(line: str =
  Field(max_length=2000)) with extra="forbid". Returns a Frame the same way.
- POST /api/reset: holder.call = make_call(), next_line = 0, returns {"ok": true}.
- Busy: /api/step and /api/say use lock.acquire(blocking=False). If already held:
  409 {"detail": "a turn is already running"}, so a double click never queues a
  second paid turn.
- RequestValidationError -> 422 {"detail": "invalid request", "fields": [last part
  of each error loc, as str]}. It never echoes the input. Any other Exception ->
  500 {"detail": "server error"}.
- Nothing logs request bodies.
"""

import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from natter.live import LiveCall
from natter.web_view import Frame, build_frame

# Sent on every response, including errors
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' data:; "
        "connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


class SayBody(BaseModel):
    """The one thing the page may send in live mode."""

    model_config = ConfigDict(extra="forbid")

    line: str = Field(max_length=2000)


@dataclass
class CallHolder:
    """The current call plus replay progress. One lock = one turn at a time."""

    call: LiveCall
    lines: list[str] | None
    next_line: int
    lock: threading.Lock


def _reply(status: int, body: dict[str, object]) -> JSONResponse:
    """A JSON response with the security headers already on it."""
    return JSONResponse(body, status_code=status, headers=SECURITY_HEADERS)


def create_app(
    mode: Literal["replay", "live"],
    make_call: Callable[[], LiveCall],
    lines: list[str] | None,
    speech_cap: int | None,
    port: int = 8000,
) -> FastAPI:
    """Build the app."""
    # No /docs, /redoc or /openapi.json
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    holder = CallHolder(make_call(), lines, 0, threading.Lock())
    app.state.holder = holder
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Wrong Host header: DNS-rebinding defence
        if request.headers.get("host") not in hosts:
            return _reply(403, {"detail": "forbidden"})
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD"):
            # Anything that changes state must come from our own page
            if origin not in origins:
                return _reply(403, {"detail": "forbidden"})
        elif origin is not None and origin not in origins:
            return _reply(403, {"detail": "forbidden"})  # GET from a foreign page
        try:
            response = await call_next(request)
        except Exception:  # never show the error, which could hold a key or scammer text
            return _reply(500, {"detail": "server error"})
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only the field names go back, never the input itself
        fields = [str(e["loc"][-1]) for e in exc.errors()]
        return _reply(422, {"detail": "invalid request", "fields": fields})

    def run_turn(line: str) -> Frame:
        """Say one line and build the frame. Caller holds the lock."""
        call = holder.call
        turns_before = len(call.state.transcript)
        previous_goal = call.state.previous_goal
        reply = call.say(line)
        return build_frame(call.state, reply, turns_before, previous_goal, speech_cap)

    @app.get("/api/mode")
    def get_mode() -> dict[str, object]:
        total = len(lines) if lines is not None else None
        return {"mode": mode, "speech_cap": speech_cap, "lines_total": total}

    @app.post("/api/step", response_model=None)
    def step() -> Frame | JSONResponse:
        if mode != "replay" or holder.lines is None:
            return _reply(404, {"detail": "not found"})
        # Never queue a second turn behind a running one
        if not holder.lock.acquire(blocking=False):
            return _reply(409, {"detail": "a turn is already running"})
        try:
            if holder.next_line >= len(holder.lines):
                return _reply(409, {"detail": "replay finished"})
            line = holder.lines[holder.next_line]
            holder.next_line += 1
            frame = run_turn(line)
            if holder.next_line == len(holder.lines):
                frame = frame.model_copy(update={"ended": True})  # last line
            return frame
        finally:
            holder.lock.release()

    @app.post("/api/say", response_model=None)
    def say(body: SayBody) -> Frame | JSONResponse:
        if mode != "live":
            return _reply(404, {"detail": "not found"})
        if not holder.lock.acquire(blocking=False):
            return _reply(409, {"detail": "a turn is already running"})
        try:
            return run_turn(body.line)
        finally:
            holder.lock.release()

    @app.post("/api/reset", response_model=None)
    def reset() -> dict[str, bool] | JSONResponse:
        # Same lock as a turn: never swap the call out from under a running turn
        if not holder.lock.acquire(blocking=False):
            return _reply(409, {"detail": "a turn is already running"})
        try:
            # Start a fresh call and rewind the replay
            holder.call = make_call()
            holder.next_line = 0
            return {"ok": True}
        finally:
            holder.lock.release()

    return app
