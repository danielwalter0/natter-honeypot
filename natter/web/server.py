"""The local web server for the Natter page. Local only; no /docs or schema page.

Every request goes through guard(): the Host must be 127.0.0.1:{port} or
localhost:{port} (the DNS-rebinding defence); a request that is not a GET must carry
our own Origin; a GET with a foreign Origin is refused. Security headers go on every
response. Only GET is served (HEAD gets 405).

Routes: GET /, /app.js, /style.css (the page files); GET /api/mode; POST /api/step
(replay only); POST /api/say (live only); POST /api/reset. Step, say and reset share
one lock: a second request while one runs gets 409, so no paid turn is ever queued.

Errors never echo input: a 422 names only known fields, a 500 says "server error".
Nothing logs request bodies.
"""

import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from natter.live import LiveCall
from natter.web_view import Frame, build_frame

PAGE_DIR = Path(__file__).parent  # index.html, app.js and style.css live next to this file
# Published path -> (file name, media type). Only these three files are ever served.
PAGE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

# Field names a 422 answer may name; any other key came from the sender
KNOWN_FIELDS = {"line", "body"}

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


def _page_route(body: str, media_type: str) -> Callable[[], Response]:
    """A route that always returns this one file.

    The route takes NO arguments on purpose: FastAPI would turn any argument into a
    query parameter, and then ?body=... could replace the page.
    """

    def serve() -> Response:
        return Response(body, media_type=media_type)

    return serve


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
        # Only names WE chose go back. An unknown key is the sender's text, so it is
        # never echoed; it is reported as "unknown field".
        fields = [
            str(e["loc"][-1]) if e["loc"][-1] in KNOWN_FIELDS else "unknown field"
            for e in exc.errors()
        ]
        return _reply(422, {"detail": "invalid request", "fields": fields})

    def run_turn(line: str) -> Frame:
        """Say one line and build the frame. Caller holds the lock."""
        call = holder.call
        turns_before = len(call.state.transcript)
        previous_goal = call.state.previous_goal
        reply = call.say(line)
        return build_frame(call.state, reply, turns_before, previous_goal, speech_cap)

    # The page files: read once, then served from memory. No path comes from the request.
    for path, (name, media_type) in PAGE_FILES.items():
        body = (PAGE_DIR / name).read_text(encoding="utf-8")
        app.add_api_route(path, _page_route(body, media_type), methods=["GET"])

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
