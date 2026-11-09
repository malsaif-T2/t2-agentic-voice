"""Ole5's knowledge base adapter when a service fails (ole5_voice/knowledge_base.py): each
failure is a ProviderError naming its step, its kind and whether asking again may pass, never
a hang; a vector of the wrong length is one; and no error, chain or log line shows the
account, the session, the question or a payload's text (GP-19). Offline on httpx's
`MockTransport` with made-up bodies (tests/ole5_voice/knowledge_support.py)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from ole5_voice.knowledge_base import QdrantKnowledgeBase
from t2_agentic_voice import ProviderError
from t2_agentic_voice.ports import Passage

from tests.leaks import holding, shown
from tests.ole5_voice.knowledge_support import (
    CALLER,
    EMAIL,
    EMBED,
    LOGIN,
    PASSWORD,
    QUERY,
    QUESTION,
    SOURCE_TEXT,
    Handler,
    Service,
    adapter,
)


def _search(kb: QdrantKnowledgeBase) -> list[Passage]:
    async def one() -> list[Passage]:
        try:
            return await kb.search(QUESTION, language="ar-SA", caller=CALLER, limit=3)
        finally:
            await kb.aclose()

    return asyncio.run(one())


def _answer(status: int, **kwargs: Any) -> Handler:
    """A handler that answers `status`, with the response's other arguments."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, **kwargs)

    return handler


def _raise(error: type[httpx.RequestError]) -> Handler:
    """A handler whose request fails with `error`, as httpx raises it."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise error("made up", request=request)

    return handler


# Each failure: the address that fails, how, and the error it gives: its kind, whether asking
# again may pass, and its details.
FAILURES = [
    (LOGIN, _answer(401), "rejected", False, {"step": "sign_in", "error": "status", "status": 401}),
    (LOGIN, _answer(200, json={}), "rejected", False, {"step": "sign_in", "error": "no_session"}),
    (
        LOGIN,
        _answer(302, headers={"location": "https://elsewhere.example/"}),
        "rejected",
        False,
        {"step": "sign_in", "error": "status", "status": 302},
    ),
    (
        LOGIN,
        _answer(503),
        "server_error",
        True,
        {"step": "sign_in", "error": "status", "status": 503},
    ),
    (
        EMBED,
        _answer(500),
        "server_error",
        True,
        {"step": "embed", "error": "status", "status": 500},
    ),
    (
        EMBED,
        _answer(200, content=b"not json"),
        "server_error",
        False,
        {"step": "embed", "error": "unreadable", "status": 200},
    ),
    (
        EMBED,
        _answer(200, json={"data": []}),
        "server_error",
        False,
        {"step": "embed", "error": "unreadable", "status": 200},
    ),
    (
        EMBED,
        _answer(200, json={"data": [{"embedding": [0.5] * 1023}]}),
        "server_error",
        False,
        {"step": "embed", "error": "wrong_vector"},
    ),
    (
        EMBED,
        _raise(httpx.ConnectError),
        "connection_lost",
        True,
        {"step": "embed", "error": "ConnectError"},
    ),
    (EMBED, _raise(httpx.ReadTimeout), "timeout", True, {"step": "embed", "error": "ReadTimeout"}),
    (QUERY, _answer(404), "rejected", False, {"step": "search", "error": "status", "status": 404}),
    (QUERY, _answer(408), "timeout", True, {"step": "search", "error": "status", "status": 408}),
    (
        QUERY,
        _answer(409),
        "server_error",
        True,
        {"step": "search", "error": "status", "status": 409},
    ),
    (
        QUERY,
        _answer(200, json={"result": {}}),
        "server_error",
        False,
        {"step": "search", "error": "unreadable", "status": 200},
    ),
    (
        QUERY,
        _raise(httpx.RemoteProtocolError),
        "connection_lost",
        True,
        {"step": "search", "error": "RemoteProtocolError"},
    ),
    (
        QUERY,
        _raise(httpx.DecodingError),  # httpx's own error, not the network's
        "server_error",
        False,
        {"step": "search", "error": "DecodingError"},
    ),
]


@pytest.mark.parametrize(("url", "handler", "kind", "retryable", "details"), FAILURES)
def test_each_failure_is_a_provider_error_naming_its_step(
    url: str,
    handler: Handler,
    kind: str,
    retryable: bool,
    details: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = Service()
    service.replace(url, handler)
    kb, _ = adapter(service)
    caplog.set_level("DEBUG")
    with pytest.raises(ProviderError) as failed:
        _search(kb)
    error = failed.value
    assert (error.kind, error.retryable, error.details) == (kind, retryable, details)
    assert error.__cause__ is None and error.__context__ is None
    [logged] = [r for r in caplog.records if r.getMessage() == "knowledge_search_failed"]
    assert vars(logged)["fields"] == {"kind": kind, **details}
    if url == LOGIN:
        assert service.at(QUERY) == []  # nothing searched without a session


def test_a_rate_limit_carries_the_delay_asked_for() -> None:
    service = Service()
    service.replace(EMBED, _answer(429, headers={"retry-after": "2"}))
    kb, _ = adapter(service)
    with pytest.raises(ProviderError) as limited:
        _search(kb)
    assert (limited.value.kind, limited.value.retry_after_s) == ("rate_limited", 2.0)
    service = Service()
    service.replace(EMBED, _answer(429, headers={"retry-after": "soon"}))
    kb, _ = adapter(service)
    with pytest.raises(ProviderError) as limited:
        _search(kb)
    assert (limited.value.kind, limited.value.retry_after_s) == ("rate_limited", None)


def test_a_service_that_does_not_answer_ends_the_search_at_its_deadline() -> None:
    """A whole search ends by its deadline, a timeout that asking again may pass, never a hang."""
    service = Service()

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)  # pragma: no cover - cut by the deadline first

    service.replace(QUERY, slow)
    kb, _ = adapter(service, deadline_s=0.05)
    with pytest.raises(ProviderError) as late:
        _search(kb)
    assert (late.value.kind, late.value.retryable) == ("timeout", True)
    assert late.value.details == {"error": "deadline"}


def test_a_failed_sign_in_is_tried_again_by_the_next_search() -> None:
    service = Service()
    service.replace(LOGIN, _answer(503))
    kb, _ = adapter(service)

    async def scene() -> list[Passage]:
        with pytest.raises(ProviderError):
            await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        del service.replaced[LOGIN]
        try:
            return await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        finally:
            await kb.aclose()

    assert len(asyncio.run(scene())) == 1
    assert service.signed_in == ["made-up-session-1"]


@pytest.mark.parametrize("failing", [LOGIN, EMBED, QUERY])
def test_no_error_or_log_line_shows_the_account_session_question_or_payload(
    failing: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Whether a search passes or fails at any step, nothing it shows holds the account's
    email or password, the session, the caller's question or a payload's text."""
    caplog.set_level("DEBUG")
    service = Service()
    kb, _ = adapter(service)
    _search(kb)  # a search that passes, whose answer holds the payload's text
    service = Service()
    if failing == QUERY:
        service.accepted = set()
    else:
        service.replace(failing, _answer(500, text=f"{EMAIL} {PASSWORD} {SOURCE_TEXT}"))
    kb, _ = adapter(service)
    with pytest.raises(ProviderError) as failed:
        _search(kb)
    surfaces = shown(failed.value, caplog=caplog, capsys=capsys)
    for value in (EMAIL, PASSWORD, "made-up-session-1", "made-up-session-2", QUESTION):
        assert holding(value, surfaces) == [], value
    for line in SOURCE_TEXT.splitlines():
        assert holding(line, surfaces) == [], line


def test_a_brief_failure_is_asked_once_more_and_the_search_passes() -> None:
    """D-078: one fault that may pass never reaches the caller."""
    service = Service()

    async def once(request: httpx.Request) -> httpx.Response:
        del service.replaced[EMBED]
        raise httpx.ReadError("made up", request=request)

    service.replace(EMBED, once)
    kb, _ = adapter(service)
    assert len(_search(kb)) >= 1


@pytest.mark.parametrize("status", [401, 429])
def test_a_refusal_or_a_rate_limit_is_not_asked_again(status: int) -> None:
    service = Service()
    calls: list[int] = []

    async def refused(request: httpx.Request) -> httpx.Response:
        calls.append(status)
        return httpx.Response(status)

    service.replace(EMBED, refused)
    kb, _ = adapter(service)
    with pytest.raises(ProviderError):
        _search(kb)
    assert len(calls) == 1


def test_a_second_failure_is_the_searchs() -> None:
    service = Service()
    calls: list[int] = []

    async def down(request: httpx.Request) -> httpx.Response:
        calls.append(503)
        return httpx.Response(503)

    service.replace(EMBED, down)
    kb, _ = adapter(service)
    with pytest.raises(ProviderError) as raised:
        _search(kb)
    assert len(calls) == 2 and raised.value.details["step"] == "embed"


def test_warming_up_signs_in_once_so_the_first_search_need_not() -> None:
    service = Service()
    kb, _ = adapter(service)

    async def scene() -> list[Passage]:
        await kb.warm_up()
        assert service.signed_in == ["made-up-session-1"]
        try:
            return await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        finally:
            await kb.aclose()

    assert len(asyncio.run(scene())) == 1
    assert service.signed_in == ["made-up-session-1"]


def test_a_warm_up_that_fails_is_logged_and_the_first_search_signs_in() -> None:
    service = Service()
    service.replace(LOGIN, _answer(503))
    kb, _ = adapter(service)

    async def scene() -> list[Passage]:
        await kb.warm_up()  # raises nothing
        assert service.signed_in == []
        del service.replaced[LOGIN]
        try:
            return await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        finally:
            await kb.aclose()

    assert len(asyncio.run(scene())) == 1
    assert service.signed_in == ["made-up-session-1"]
