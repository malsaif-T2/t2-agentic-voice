"""Ole5's knowledge base (plan 006, Q4 and Q14): a `KnowledgeBase`, the library's port
(`t2_agentic_voice.ports`), over T2's embedding service and T2's Qdrant behind T2's sign-in
gateway, by plain HTTP: one embedding and one search per question. It stays in the app (the
owner's Q14); the library gives every team the port and `knowledge_tool`.

The wire, as plan 006's spike saw it on 2026-11-06:
- **Sign-in.** A form post of `email` and `password` to the gateway's login URL, which sets its
  session cookie (`SESSION_COOKIE`). That cookie is sent, as a header, to Qdrant alone, never
  to the embedding service or the gateway: the client keeps no cookie a response sets (its jar
  refuses every one), so none travels by itself. On a 401 from Qdrant the adapter signs in
  again once, under a lock and only if no other search signed in meanwhile, and asks once more.
- **The embedding.** `POST {embedding_url}/v1/embed` with the question; the vector is
  `data[0].embedding`, `DIMENSIONS` finite floats, checked. No sign-in.
- **The search.** `POST {qdrant_url}/collections/default/points/query`: the dense vector with
  the tenant's filter on `group_id`, never left out (the collection is shared by tenants, and
  indexed per tenant only), at most `limit` points with their payload, best first. The points
  become passages as passages.py says.

**Connections.** One client an adapter, and the app builds one adapter a process, for T2's
host: it keeps a connection open five minutes (`LIMITS`; the prototype's D41: reconnecting put
about 1 s on the first sound after a search). The port has no `aclose` (TD-113), so the adapter
has its own, which the app's lifespan awaits.

**Timeouts** are a tool's: each request connects within 2 s and reads within 3 s (`TIMEOUT`),
and a whole search, a second sign-in included, ends within `deadline_s` (4 s by default), under
the knowledge tool's own timeout.

**Failures.** Every failure is a `ProviderError` (the port's rule), which the talker's tool
turns into "I cannot look that up now", never a hang. Its details name the step (`sign_in`,
`embed`, `search`), the failure and the HTTP status, never a value: no email, password,
cookie, question, vector or payload text is in an error, its chain or a log line. It is raised
outside the handler, so no exception chain leads to httpx's error, which holds the request. A
cancel is never caught: the request stops at once.

`language` and `caller` are the port's, unused: Ole5's points serve every caller alike, and one
embedding serves both languages (bge-m3).
"""

from __future__ import annotations

import asyncio
import math
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, ValidationError
from t2_agentic_voice import Caller, ProviderError, get_logger
from t2_agentic_voice.ports import Passage

from ole5_voice.passages import passages
from ole5_voice.settings import KnowledgeAccess

log = get_logger(__name__)

Step = Literal["sign_in", "embed", "search"]

COLLECTION: Final = "default"
# The gateway's session cookie, which Qdrant reads.
SESSION_COOKIE: Final = "ole5_session"
# The payload field that names a point's tenant, which every search filters on.
TENANT_FIELD: Final = "group_id"
# The named dense vector, and its size (bge-m3).
VECTOR: Final = "dense"
DIMENSIONS: Final = 1024
TIMEOUT: Final = httpx.Timeout(3.0, connect=2.0, pool=1.0)
LIMITS: Final = httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=300.0)
DEADLINE_S: Final = 4.0


class _Answer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)


class _Embedding(_Answer):
    embedding: list[float]


class _Embedded(_Answer):
    """The embedding service's answer: one embedding for the one input."""

    data: list[_Embedding] = Field(min_length=1)


class _Found(_Answer):
    points: list[JsonValue]


class _Queried(_Answer):
    """Qdrant's answer to a query: the points, each read on its own (passages.py)."""

    result: _Found


class QdrantKnowledgeBase:
    """Ole5's knowledge base behind the library's port (the module's docstring), reached with
    `access`; `transport` stands in for the network in a test."""

    def __init__(
        self,
        access: KnowledgeAccess,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        deadline_s: float = DEADLINE_S,
    ) -> None:
        self._access = access
        self._qdrant = access.qdrant_url.rstrip("/")
        self._embedding = access.embedding_url.rstrip("/")
        self._deadline_s = deadline_s
        self._client = httpx.AsyncClient(
            transport=transport,
            limits=LIMITS,
            timeout=TIMEOUT,
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        )
        self._session: SecretStr | None = None
        self._signing_in = asyncio.Lock()

    async def search(
        self, query: str, *, language: str, caller: Caller, limit: int
    ) -> list[Passage]:
        """The passages that answer `query`, best first, at most `limit`: one embedding and one
        search; none for a question with no words. ValueError for a limit under 1;
        ProviderError on a failure."""
        if limit < 1:
            raise ValueError("a search reads at least one passage")
        words = query.strip()
        if not words:
            return []
        failure: ProviderError | None = None
        try:
            async with asyncio.timeout(self._deadline_s):
                vector = await self._embed(words)
                points = await self._query(vector, limit)
        except ProviderError as error:
            failure = error
        except TimeoutError:
            failure = ProviderError("timeout", True, details={"error": "deadline"})
        if failure is not None:  # raised here, outside the handlers: no chain to a request
            log.warning("knowledge_search_failed", kind=failure.kind, **failure.details)
            raise failure
        return passages(points)[:limit]  # at most `limit`, whatever the answer held

    async def aclose(self) -> None:
        """Close the client and its kept-open connections; a search after it fails."""
        await self._client.aclose()

    async def _embed(self, words: str) -> list[float]:
        body = {"input": words, "return_sparse": False, "include_stats": False}
        response = await self._post("embed", f"{self._embedding}/v1/embed", json=body)
        embedded = _read("embed", response, _Embedded)
        vector = embedded.data[0].embedding
        if len(vector) != DIMENSIONS or not all(math.isfinite(x) for x in vector):
            raise ProviderError("server_error", False, details=_details("embed", "wrong_vector"))
        return vector

    async def _query(self, vector: list[float], limit: int) -> list[JsonValue]:
        body = {
            "query": vector,
            "using": VECTOR,
            "filter": {"must": [{"key": TENANT_FIELD, "match": {"value": self._access.tenant}}]},
            "limit": limit,
            "with_payload": True,
        }
        url = f"{self._qdrant}/collections/{COLLECTION}/points/query"
        session = await self._signed_in()
        response = await self._post("search", url, json=body, headers=_cookie(session))
        if response.status_code == httpx.codes.UNAUTHORIZED:
            session = await self._signed_in_again(session)
            response = await self._post("search", url, json=body, headers=_cookie(session))
        return _read("search", response, _Queried).result.points

    async def _signed_in(self) -> SecretStr:
        """The session, signed in first when there is none yet: one sign-in at a time."""
        async with self._signing_in:
            if self._session is None:
                self._session = await self._sign_in()
            return self._session

    async def _signed_in_again(self, refused: SecretStr) -> SecretStr:
        """A new session in place of `refused`, which Qdrant refused: signed in again unless
        another search did so meanwhile."""
        async with self._signing_in:
            if self._session is None or self._session is refused:
                self._session = None  # a failed sign-in leaves none, so the next search tries
                self._session = await self._sign_in()
            return self._session

    async def _sign_in(self) -> SecretStr:
        access = self._access
        form = {"email": access.login_email, "password": access.login_password.get_secret_value()}
        response = await self._post("sign_in", access.login_url, data=form)
        failure = _status("sign_in", response)
        if failure is not None:
            raise failure
        session = response.cookies.get(SESSION_COOKIE)
        if not session:
            raise ProviderError("rejected", False, details=_details("sign_in", "no_session"))
        log.info("knowledge_base_signed_in")
        return SecretStr(session)

    async def _post(self, step: Step, url: str, **request: Any) -> httpx.Response:
        """The answer to one POST; a ProviderError for a request that failed, raised outside
        the handler so its chain holds no request."""
        if self._client.is_closed:
            raise ProviderError("server_error", False, details=_details(step, "closed"))
        try:
            return await self._client.post(url, **request)
        except httpx.TimeoutException as error:
            failure = ProviderError("timeout", True, details=_details(step, error))
        except httpx.TransportError as error:
            failure = ProviderError("connection_lost", True, details=_details(step, error))
        except httpx.HTTPError as error:
            failure = ProviderError("server_error", False, details=_details(step, error))
        raise failure


def _read[M: BaseModel](step: Step, response: httpx.Response, model: type[M]) -> M:
    """`response`'s body as `model`; a ProviderError for a failed status or a body that cannot
    be read, its text never shown."""
    failure = _status(step, response)
    if failure is not None:
        raise failure
    try:
        return model.model_validate_json(response.content)
    except ValidationError:
        unreadable = ProviderError(
            "server_error", False, details=_details(step, "unreadable", response.status_code)
        )
    raise unreadable


def _status(step: Step, response: httpx.Response) -> ProviderError | None:
    """The ProviderError for a status that is not a success, None for one that is: asking again
    may pass after a 408, 409, 429 or 5xx; any other is refused (a redirect too, never
    followed: it would carry the form or the cookie to another address)."""
    status = response.status_code
    if httpx.codes.is_success(status):
        return None
    details = _details(step, "status", status)
    if status == httpx.codes.TOO_MANY_REQUESTS:
        return ProviderError("rate_limited", True, _retry_after(response), details=details)
    if status == httpx.codes.REQUEST_TIMEOUT:
        return ProviderError("timeout", True, details=details)
    if status == httpx.codes.CONFLICT or status >= httpx.codes.INTERNAL_SERVER_ERROR:
        return ProviderError("server_error", True, details=details)
    return ProviderError("rejected", False, details=details)


def _retry_after(response: httpx.Response) -> float | None:
    """The delay a `retry-after` header asks for, in seconds; None unless it is a finite number
    of seconds, 0 or more."""
    try:
        seconds = float(response.headers.get("retry-after") or "")
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _details(step: Step, error: Exception | str, status: int | None = None) -> dict[str, JsonValue]:
    """A failure's details: its step, the failure's name (an exception's class, never its text)
    and the HTTP status, if any."""
    name = error if isinstance(error, str) else type(error).__name__
    details: dict[str, JsonValue] = {"step": step, "error": name}
    if status is not None:
        details["status"] = status
    return details


def _cookie(session: SecretStr) -> dict[str, str]:
    """The header that carries the session to Qdrant."""
    return {"Cookie": f"{SESSION_COOKIE}={session.get_secret_value()}"}
