"""Spike: time Groq text-to-speech for three granny lines. Not product code."""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "canopylabs/orpheus-v1-english"  # Groq's English TTS model (docs checked 2026-11-19)
VOICES = ["autumn", "diana", "hannah", "austin", "daniel", "troy"]  # all English voices
VOICE = "diana"  # default voice for the three-line run
OUT_DIR = Path("spike_out")
LINES = [  # Orpheus accepts at most 200 characters per request
    "Hello? Who is this, dear?",
    "Oh, the bank? My grandson usually handles that. Can you hold on while I find my glasses?",
    "Now let me see, you said my account was compromised? I wrote it down somewhere, "
    "next to the cat food list. Could you spell your name again, slowly, so I get it right?",
]


def read_key() -> str:
    # Parse .env by hand so we need no new dependency; the key is never printed.
    for line in Path(".env").read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "GROQ_API_KEY":
            return value.strip().strip('"')
    raise SystemExit("GROQ_API_KEY not found in .env")


def speak(key: str, text: str, out: Path, voice: str = VOICE) -> None:
    body = json.dumps({"model": MODEL, "voice": voice, "input": text, "response_format": "wav"})
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "natter-spike/0.1",  # Cloudflare blocks urllib's default agent (error 1010)
    }
    start = time.perf_counter()
    try:
        # Request is built inside urlopen with a literal URL so ruff (S310) sees a fixed https URL.
        with urllib.request.urlopen(
            urllib.request.Request(
                "https://api.groq.com/openai/v1/audio/speech", data=body.encode(), headers=headers
            ),
            timeout=60,
        ) as resp:
            first = resp.read(1)  # blocks until the first audio byte arrives
            first_byte = time.perf_counter() - start
            audio = first + resp.read()  # the rest of the file
    except urllib.error.HTTPError as err:
        # Show Groq's error body (e.g. "accept the model terms"); it never contains the key.
        raise SystemExit(f"HTTP {err.code}: {err.read().decode(errors='replace')}") from err
    total = time.perf_counter() - start
    out.write_bytes(audio)
    print(f"{out.name}: first byte {first_byte:.2f}s, total {total:.2f}s, {len(audio):,} bytes")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    key = read_key()
    if "--voices" in sys.argv:  # comparison mode: same medium line in every voice
        for name in VOICES:
            speak(key, LINES[1], OUT_DIR / f"voice_{name}.wav", name)
        raise SystemExit(0)
    files = [OUT_DIR / f"line{i}.wav" for i in range(1, len(LINES) + 1)]
    for text, path in zip(LINES, files, strict=True):
        speak(key, text, path)
    os.startfile(files[0])  # noqa: S606 - Windows only: open in the default audio player
