"""A fake Scribe v3 Live socket for the streaming adapter's tests and the bridge's (no network):
`FakeScribe` sends `session_started` as each session opens, answers each commit from its script
in order, and keeps every message sent; with what a test reads of them."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import SecretStr
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT

from tests.t2_agentic_voice.adapters.provider_support import KEY, FakeProvider, Reply, answering

STARTED = json.dumps({"message_type": "session_started", "session_id": "s-1", "config": {}})
# What batch Scribe answers in the bridge's tests, when a turn goes by request.
BATCH_WORDS = "heard by request"


def said(text: str, kind: str = "committed_transcript") -> str:
    """A server message of `kind` holding `text`."""
    return json.dumps({"message_type": kind, "text": text}, ensure_ascii=False)


def refused(kind: str, text: str = "") -> str:
    """An error message of `kind`, its text the provider's own (never shown)."""
    return json.dumps({"message_type": kind, "error": text})


# One commit's answer: its words, any other reply (an error message, a close), or None for none.
Answer = str | Reply | None


@dataclass
class FakeScribe:
    """Scribe v3 Live on a fake socket: `started` sent as each session opens, `open_s` after it
    was asked, each commit then answered by the next of `answers` (words are a
    `committed_transcript`, after the `committed_transcript_with_timestamps` the real one sends
    too) after `delay_s`."""

    answers: list[Answer] = field(default_factory=list)
    started: Sequence[Reply] = (STARTED,)
    delay_s: float = 0.0
    open_s: float = 0.0
    sent: list[str] = field(default_factory=list)
    opened: list[tuple[str, dict[str, str], float]] = field(default_factory=list)
    closes: int = 0

    async def opener(self, url: str, headers: Mapping[str, str], timeout_s: float) -> FakeScribe:
        await asyncio.sleep(self.open_s)
        self.opened.append((url, dict(headers), timeout_s))
        self._replies: asyncio.Queue[Reply] = asyncio.Queue()
        for reply in self.started:
            self._replies.put_nowait(reply)
        return self

    async def send(self, message: str | bytes) -> None:
        assert isinstance(message, str)
        self.sent.append(message)
        if not json.loads(message)["commit"]:
            return
        answer = self.answers.pop(0) if self.answers else ""
        if answer is None:
            return
        replies: list[Reply] = [answer]
        if isinstance(answer, str) and not answer.startswith("{"):  # words, not a message
            replies = [said(answer, "committed_transcript_with_timestamps"), said(answer)]
        asyncio.get_running_loop().call_later(self.delay_s, self._put, replies)

    def _put(self, replies: list[Reply]) -> None:
        for reply in replies:
            self._replies.put_nowait(reply)

    async def recv(self) -> str | bytes:
        reply = await self._replies.get()
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def close(self) -> None:
        self.closes += 1

    def messages(self) -> list[dict[str, object]]:
        """Every message sent, read as JSON."""
        return [json.loads(message) for message in self.sent]

    def commits(self) -> int:
        """How many commits were sent."""
        return sum(1 for message in self.messages() if message["commit"])

    def audio(self) -> bytes:
        """The audio sent, every message's joined."""
        return b"".join(base64.b64decode(str(m["audio_base_64"])) for m in self.messages())


def scribe_stt(scribe: FakeScribe, batch: FakeProvider | None = None) -> ElevenLabsSTT:
    """ElevenLabs' adapter streaming to `scribe`, its batch requests to `batch` (by default one
    that answers `BATCH_WORDS` to each)."""
    batch = batch or FakeProvider(answering(200, {"text": BATCH_WORDS, "language_code": "eng"}))
    return ElevenLabsSTT(
        api_key=SecretStr(KEY), timeout_s=2.0, transport=batch.transport(), opener=scribe.opener
    )
