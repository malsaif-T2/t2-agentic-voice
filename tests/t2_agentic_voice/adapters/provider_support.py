"""What the tests of the adapters of the providers measured beside Groq share: a fake provider
on httpx's MockTransport (no network), a multipart reader that keeps repeated fields, a made-up
key, a clip, and the settings that carry the key."""

from __future__ import annotations

import json
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

KEY = "made-up-provider-key-0123456789"
# A second of audio, and words a transcript holds, that no error or log line may show.
CLIP = AudioClip(pcm16=b"".join(struct.pack("<h", (i * 89) % 4096 - 2048) for i in range(16_000)))
HEARD = "made-up caller words 4471"

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeProvider:
    """A provider that answers each request with `handler`'s response, keeping every request."""

    handler: Handler
    requests: list[httpx.Request] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        def answer(request: httpx.Request) -> httpx.Response:
            request.read()
            self.requests.append(request)
            return self.handler(request)

        return httpx.MockTransport(answer)


def answering(status: int, body: object, headers: dict[str, str] | None = None) -> Handler:
    """A handler that answers every request with `status` and `body` as JSON (bytes as given)."""
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return lambda request: httpx.Response(status, content=content, headers=headers)


def raising(error: Exception) -> Handler:
    """A handler that fails every request with `error`, as the transport would."""

    def fail(request: httpx.Request) -> httpx.Response:
        raise error

    return fail


def fields(request: httpx.Request) -> list[tuple[str, dict[str, str], bytes]]:
    """The multipart body's parts in order, a repeated field once a part: each one's name, its
    headers (lowercase names) and its bytes."""
    kind, _, boundary = request.headers["content-type"].partition("; boundary=")
    chunks = request.content.split(b"--" + boundary.encode())
    assert (kind, chunks[0], chunks[-1]) == ("multipart/form-data", b"", b"--\r\n")
    found = []
    for chunk in chunks[1:-1]:
        head, _, data = chunk.removeprefix(b"\r\n").removesuffix(b"\r\n").partition(b"\r\n\r\n")
        lines = [line.decode().split(": ", 1) for line in head.split(b"\r\n")]
        headers = {name.lower(): value for name, value in lines}
        found.append((headers["content-disposition"].split('"')[1], headers, data))
    return found


def texts(request: httpx.Request) -> dict[str, list[str]]:
    """The multipart body's text fields by name, each with its values in order."""
    found: dict[str, list[str]] = {}
    for name, headers, data in fields(request):
        if "filename" not in headers["content-disposition"]:
            found.setdefault(name, []).append(data.decode())
    return found


def keyed(group: str, **stt: object) -> VoiceSettings:
    """Test settings with the made-up key in `group` and `stt` given."""
    return VoiceSettings.model_validate({"env": "test", group: {"api_key": KEY}, "stt": stt})
