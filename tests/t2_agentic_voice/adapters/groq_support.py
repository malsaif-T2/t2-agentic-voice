"""What the Groq adapter's tests share (test_groq_stt.py, test_groq_stt_checks.py): made-up keys,
Block 0's fixed clip and baseline request, a fake Groq answering on a fake transport, and one
transcription through the adapter. Nothing leaves the machine."""

from __future__ import annotations

import json
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript

FIXTURE = Path(__file__).parents[1] / "fixtures" / "groq_stt_request.json"
BASELINE = json.loads(FIXTURE.read_text(encoding="utf-8"))
KEY, OTHER = "made-up-settings-key-0123", "made-up-shell-key-4567"
SETTING = "T2V_GROQ__API_KEY"
# Block 0's fixed clip: 1 s at 16 kHz, sample i = (i * 97) % 4096 - 2048.
CLIP = AudioClip(pcm16=b"".join(struct.pack("<h", (i * 97) % 4096 - 2048) for i in range(16_000)))
SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 0.6, "avg_logprob": -0.2, "no_speech_prob": 0.1},
    {"id": 1, "start": 0.6, "end": 1.0, "avg_logprob": -0.5, "no_speech_prob": 0.3},
    {"id": 2, "start": 1.0, "end": 2.0},  # gives neither value: weighs in neither
]
ANSWER = {"text": "  made-up words ", "language": "Arabic", "segments": SEGMENTS, "x_groq": {}}

Reply = httpx.Response | Exception | Callable[[httpx.Request], Awaitable[httpx.Response]]


class FakeGroq(httpx.AsyncBaseTransport):
    """Answers each request with its next reply, keeping every request it receives."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies) or [httpx.Response(200, json=ANSWER)]
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, httpx.Response) else await reply(request)


def groq_settings(timeout_s: float = 6.0, **groq: Any) -> VoiceSettings:
    """Settings holding the made-up `KEY`, unless `groq` gives the group's values."""
    given = GroqSettings(**({"api_key": SecretStr(KEY)} | groq))
    return VoiceSettings(env="test", groq=given, stt=SttSettings(timeout_s=timeout_s))


async def call(fake: httpx.AsyncBaseTransport, clip: AudioClip = CLIP, **given: Any) -> Transcript:
    """One transcription of `clip` (in Arabic, with no prompt, unless `given` says) through an
    adapter built from `groq_settings(**given)` on the `fake` transport, closed after it."""
    language, prompt = given.pop("language", "ar"), given.pop("prompt", None)
    adapter = GroqSTT.from_settings(groq_settings(**given), transport=fake)
    try:
        return await adapter.transcribe(clip, language=language, prompt=prompt)
    finally:
        await adapter.aclose()


def parts(request: httpx.Request) -> dict[str, tuple[dict[str, str], bytes]]:
    """The multipart body's parts by field name: each one's headers (lowercase names) and bytes."""
    kind, _, boundary = request.headers["content-type"].partition("; boundary=")
    chunks = request.content.split(b"--" + boundary.encode())
    assert (kind, chunks[0], chunks[-1]) == ("multipart/form-data", b"", b"--\r\n")
    found = {}
    for chunk in chunks[1:-1]:
        head, _, data = chunk.removeprefix(b"\r\n").removesuffix(b"\r\n").partition(b"\r\n\r\n")
        lines = [line.decode().split(": ", 1) for line in head.split(b"\r\n")]
        headers = {name.lower(): value for name, value in lines}
        found[headers["content-disposition"].split('"')[1]] = (headers, data)
    return found
