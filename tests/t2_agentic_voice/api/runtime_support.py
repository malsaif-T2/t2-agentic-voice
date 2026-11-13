"""What the runtime's tests share (plan 003): a runtime built on the fakes of fakes.py, served
in-process through httpx's ASGI transport with its lifespan run, and fakes of the parts the
lifespan opens (the phrase cache, the used-token store and the identity sources), so these tests
run on the ports' contracts alone.

`patch_stores` (the `patched_stores` fixture of this folder's conftest.py) swaps the adapters'
`PhraseCache` and `SqliteUsedTokens` for fakes, which the runtime imports when its lifespan
starts.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from fastapi import FastAPI
from t2_agentic_voice.adapters import phrase_cache, used_tokens
from t2_agentic_voice.api.protocol import BODIES, OFFER_SECRET_HEADER
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import JoinRejected
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.identity import JoinContext
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.voice.calls import Calls

from tests.t2_agentic_voice.fakes import FakeCalls, FakeClock, FakeSpeechToText, FakeTextToSpeech

AGENT = VoiceAgent(
    name="echo",
    languages=[Language.english(greeting="Hello there."), Language.saudi_arabic(greeting="هلا.")],
)
PREFIX = "/voice"
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJlLTEifQ.zx-made-up-signature"
OFFER_SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\n"
END = {"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}
LINE = {
    "candidate": "candidate:1 1 udp 2122260223 192.0.2.10 50000 typ host",
    "sdp_mid": "0",
    "sdp_mline_index": 0,
}
LOOPBACK = ("127.0.0.1", 50000)
PLAIN = Consent(version=None, record_audio=False)


def dev_settings(tmp_path: Path, **groups: Any) -> VoiceSettings:
    """Settings a router serves (`env` dev; `test` is refused), under the test's own folder."""
    return VoiceSettings(env="dev", storage=StorageSettings(var_dir=tmp_path / "var"), **groups)


class FakeIdentity:
    """An identity source that gives every token `caller` and `consent`, or refuses each with
    `JoinRejected`; it keeps each token and join it was asked about."""

    def __init__(
        self,
        *,
        caller: Caller | None = None,
        consent: Consent = PLAIN,
        refuse: bool = False,
    ) -> None:
        self.caller = caller or Caller(subject="caller-1")
        self.consent = consent
        self.refuse = refuse
        self.asked: list[tuple[str, JoinContext]] = []

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        self.asked.append((token, join))
        if self.refuse:
            raise JoinRejected("The token was refused, as the fake was told to.")
        return self.caller, self.consent


class FakeUsedTokens:
    """The used-token store, in memory: `open` records each path it was given."""

    opened: ClassVar[list[Path]] = []

    def __init__(self) -> None:
        self.used: set[str] = set()
        self.closed = False

    @classmethod
    async def open(cls, path: Path) -> FakeUsedTokens:
        cls.opened.append(path)
        return cls()

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        first = token_id not in self.used
        self.used.add(token_id)
        return first

    async def aclose(self) -> None:
        self.closed = True


class FakePhraseCache:
    """The phrase cache: it declares nothing and holds no audio; each one built is kept, with
    the agent it declared."""

    built: ClassVar[list[FakePhraseCache]] = []
    failure: ClassVar[BaseException | None] = None

    def __init__(self, tts: TextToSpeech, folder: Path) -> None:
        self.tts = tts
        self.folder = folder
        self.declared: VoiceAgent | None = None
        FakePhraseCache.built.append(self)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, tts: TextToSpeech, *, folder: Path
    ) -> FakePhraseCache:
        return cls(tts, folder)

    async def declare(self, agent: VoiceAgent) -> int:
        if FakePhraseCache.failure is not None:
            raise FakePhraseCache.failure
        self.declared = agent
        return 0

    def audio(self, text: str, *, language: str) -> AudioChunk:
        raise LookupError("not a phrase declared at the start")


def patch_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the adapters' phrase cache and used-token store for the fakes above."""
    monkeypatch.setattr(phrase_cache, "PhraseCache", FakePhraseCache)
    monkeypatch.setattr(used_tokens, "SqliteUsedTokens", FakeUsedTokens)
    FakePhraseCache.built, FakePhraseCache.failure = [], None
    FakeUsedTokens.opened = []


@dataclass
class Harness:
    """A runtime of `agent` on the fakes, and the fakes it was given."""

    settings: VoiceSettings
    agent: VoiceAgent = AGENT
    identity: FakeIdentity = field(default_factory=FakeIdentity)
    calls: FakeCalls = field(default_factory=FakeCalls)
    clock: FakeClock = field(default_factory=FakeClock)
    stt: FakeSpeechToText = field(default_factory=FakeSpeechToText)
    tts: FakeTextToSpeech = field(default_factory=FakeTextToSpeech)
    built: list[dict[str, Any]] = field(default_factory=list)
    runtime: VoiceRuntime = field(init=False)

    def __post_init__(self) -> None:
        def calls(**given: Any) -> Calls:
            self.built.append(given)
            return self.calls

        self.runtime = VoiceRuntime(
            self.agent,
            settings=self.settings,
            identity=self.identity,
            providers=Providers(stt=self.stt, tts=self.tts),
            _calls=calls,
            _clock=self.clock,
        )

    def app(self, *, dev: bool = False) -> FastAPI:
        """A plain FastAPI app that includes the runtime's router under PREFIX."""
        app = FastAPI()
        app.include_router(self.runtime._router(dev=dev), prefix=PREFIX)
        return app


def client(app: FastAPI, *, peer: tuple[str, int] = LOOPBACK) -> httpx.AsyncClient:
    """An HTTP client of `app`, in-process, as the peer `peer`."""
    transport = httpx.ASGITransport(app=app, client=peer)
    return httpx.AsyncClient(transport=transport, base_url="http://t2v.test")


@asynccontextmanager
async def serving(
    app: FastAPI, *, peer: tuple[str, int] = LOOPBACK
) -> AsyncIterator[httpx.AsyncClient]:
    """A client of `app` while its lifespan runs."""
    async with app.router.lifespan_context(app), client(app, peer=peer) as http:
        yield http


async def post(http: httpx.AsyncClient, path: str, body: object, **headers: str) -> httpx.Response:
    """`body` sent as JSON to `path` under PREFIX."""
    return await http.post(
        PREFIX + path,
        content=json.dumps(body),
        headers={"content-type": "application/json", **headers},
    )


async def patch(http: httpx.AsyncClient, body: object, **headers: str) -> httpx.Response:
    """`body` sent as JSON to `PATCH /offer`."""
    return await http.patch(
        PREFIX + "/offer",
        content=json.dumps(body),
        headers={"content-type": "application/json", **headers},
    )


async def joined(http: httpx.AsyncClient, **extra: object) -> tuple[str, str]:
    """A new call's ID and offer secret, from `/join`."""
    answer = await post(http, "/join", {"token": TOKEN, "protocol": 1, **extra})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    return body["call_id"], body["offer_secret"]


async def offered(http: httpx.AsyncClient, call_id: str, secret: str) -> httpx.Response:
    """The call's offer, its secret in the body."""
    return await post(
        http,
        "/offer",
        {"call_id": call_id, "sdp": OFFER_SDP, "type": "offer", "offer_secret": secret},
    )


async def candidates(
    http: httpx.AsyncClient, call_id: str, secret: str, *lines: dict[str, object]
) -> httpx.Response:
    """The call's candidates (the end of candidates unless given), its secret in the header."""
    body = {"call_id": call_id, "candidates": list(lines or (END,))}
    return await patch(http, body, **{OFFER_SECRET_HEADER: secret})


def refused(answer: httpx.Response, route: str, code: str) -> dict[str, Any]:
    """`answer`'s error body, checked to be `code` at a status `route`'s BODIES entry lists for
    it, in the one error shape."""
    body: dict[str, Any] = answer.json()
    assert body["code"] == code, body
    assert code in BODIES[route].errors[answer.status_code], (route, answer.status_code, code)
    assert set(body) == {"code", "message", "notice", "reference"}
    assert (body["notice"] is not None) == (code == "protocol_mismatch")
    return body
