"""A made-up stand-in for T2's sign-in gateway, embedding service and Qdrant, on httpx's
`MockTransport`, for the tests of Ole5's knowledge base adapter (ole5_voice/knowledge_base.py).
Every address, account, session and body here is made up; nothing reaches a network."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
from ole5_voice.knowledge_base import DIMENSIONS, QdrantKnowledgeBase
from ole5_voice.settings import KnowledgeAccess
from pydantic import SecretStr
from t2_agentic_voice import Caller

LOGIN = "https://kb.example/gateway/login"
EMBED = "https://kb.example/embed/v1/embed"
QUERY = "https://kb.example/team/qdrant/collections/default/points/query"
EMAIL = "someone@example.com"
PASSWORD = "a-made-up-password-0123"
TENANT = "made-up-tenant"
QUESTION = "how do I archive a made-up correspondence"
CALLER = Caller(subject="someone")
ACCESS = KnowledgeAccess(
    qdrant_url="https://kb.example/team/qdrant/",
    login_url=LOGIN,
    login_email=EMAIL,
    login_password=SecretStr(PASSWORD),
    embedding_url="https://kb.example/embed",
    tenant=TENANT,
)
VECTOR = [0.001 * n for n in range(DIMENSIONS)]
# A payload's text, made up, which no error or log line may show.
SOURCE_TEXT = "Archiving a made-up item\n1. Open the made-up item.\n2. Press **Archive**."


def point(
    chunk: str = "chunk_003",
    *,
    score: float = 0.71,
    document: str = "A made-up guide",
    **metadata: Any,
) -> dict[str, Any]:
    """One point as Qdrant answers a query with its payload."""
    meta = {"document_name": document, "chunk_id": chunk, "source_text": SOURCE_TEXT} | metadata
    payload = {"group_id": TENANT, "page_content": "A summary.\n\n" + SOURCE_TEXT, "metadata": meta}
    return {"id": "made-up-id", "version": 1, "score": score, "payload": payload}


Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


class Service:
    """Answers each request by its address, as the three services would, and keeps every
    request: the gateway signs in `EMAIL` with `PASSWORD`, setting the next of `sessions` (and a
    cookie of its own, `other`); the embedding service answers `vector` (setting a cookie,
    `tracking`); Qdrant answers `points` to a request with a session it accepts (`accepted`,
    each session signed in by default), and 401 to any other. `replace` answers one address
    with a handler of the test's own."""

    def __init__(self, *, sessions: tuple[str, ...] = ("made-up-session-1", "made-up-session-2")):
        self.sessions = list(sessions)
        self.accepted: set[str] | None = None
        self.signed_in: list[str] = []
        self.vector: list[float] = VECTOR
        self.points: list[dict[str, Any]] = [point("chunk_003"), point("chunk_007", score=0.64)]
        self.requests: list[httpx.Request] = []
        self.replaced: dict[str, Handler] = {}

    def at(self, url: str) -> list[httpx.Request]:
        """The requests sent to `url`, in order."""
        return [request for request in self.requests if str(request.url) == url]

    def replace(self, url: str, handler: Handler) -> None:
        self.replaced[url] = handler

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url in self.replaced:
            return await self.replaced[url](request)
        if url == LOGIN:
            return self._sign_in(request)
        if url == EMBED:
            body = {"data": [{"embedding": self.vector}]}
            return httpx.Response(200, json=body, headers={"set-cookie": "tracking=1; Path=/"})
        if url == QUERY:
            return self._query(request)
        return httpx.Response(404)

    def _sign_in(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        if form != {"email": [EMAIL], "password": [PASSWORD]}:
            return httpx.Response(401)
        session = self.sessions.pop(0)
        self.signed_in.append(session)
        cookies = [f"ole5_session={session}; Path=/; Secure; HttpOnly", "other=x; Path=/"]
        headers = [("set-cookie", cookie) for cookie in cookies]
        return httpx.Response(200, json={"reviewer": "made up"}, headers=headers)

    def _query(self, request: httpx.Request) -> httpx.Response:
        accepted = set(self.signed_in) if self.accepted is None else self.accepted
        if request.headers.get("cookie") not in {f"ole5_session={s}" for s in accepted}:
            return httpx.Response(401, json={"status": "made up"})
        answer = {"result": {"points": self.points}, "status": "ok", "time": 0.001}
        return httpx.Response(200, json=answer)


class Transport(httpx.MockTransport):
    """httpx's mock transport, counting the times it was closed."""

    def __init__(self, service: Service) -> None:
        super().__init__(service.handle)
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


def adapter(service: Service, **options: Any) -> tuple[QdrantKnowledgeBase, Transport]:
    """An adapter on `service`, and its transport."""
    transport = Transport(service)
    return QdrantKnowledgeBase(ACCESS, transport=transport, **options), transport


def body(request: httpx.Request) -> Any:
    """A request's JSON body."""
    return json.loads(request.content)
