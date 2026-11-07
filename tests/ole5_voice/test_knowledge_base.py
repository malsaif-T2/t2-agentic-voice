"""Ole5's knowledge base adapter on the wire (ole5_voice/knowledge_base.py), offline on httpx's
`MockTransport` with made-up bodies (tests/ole5_voice/knowledge_support.py): the sign-in, the
session's cookie sent to Qdrant alone, a second sign-in once on a 401, the embedding's and the
search's bodies with the tenant's filter always there, the points made passages, and one
client kept open between searches and closed by `aclose`. Its failures:
test_knowledge_base_failures.py."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from ole5_voice.knowledge_base import (
    DEADLINE_S,
    DIMENSIONS,
    LIMITS,
    TIMEOUT,
    QdrantKnowledgeBase,
)
from t2_agentic_voice import ProviderError, Tool
from t2_agentic_voice.ports import KnowledgeBase, Passage

from tests.ole5_voice.knowledge_support import (
    CALLER,
    EMBED,
    LOGIN,
    QUERY,
    QUESTION,
    SOURCE_TEXT,
    TENANT,
    VECTOR,
    Service,
    adapter,
    body,
)


def _search(kb: QdrantKnowledgeBase, query: str = QUESTION, limit: int = 3) -> list[Passage]:
    return asyncio.run(_one(kb, query, limit))


async def _one(kb: QdrantKnowledgeBase, query: str, limit: int) -> list[Passage]:
    try:
        return await kb.search(query, language="ar-SA", caller=CALLER, limit=limit)
    finally:
        await kb.aclose()


def test_the_adapter_meets_the_librarys_port() -> None:
    kb, _ = adapter(Service())
    port: KnowledgeBase = kb
    assert port is kb
    asyncio.run(kb.aclose())


def test_a_search_signs_in_embeds_the_question_and_searches_the_tenants_points() -> None:
    service = Service()
    kb, _ = adapter(service)
    found = _search(kb, f"  {QUESTION} ", limit=3)
    assert [str(request.url) for request in service.requests] == [EMBED, LOGIN, QUERY]
    assert all(request.method == "POST" for request in service.requests)
    [login] = service.at(LOGIN)
    assert login.headers["content-type"] == "application/x-www-form-urlencoded"
    [embed] = service.at(EMBED)
    assert body(embed) == {"input": QUESTION, "return_sparse": False, "include_stats": False}
    [query] = service.at(QUERY)
    assert body(query) == {
        "query": VECTOR,
        "using": "dense",
        "filter": {"must": [{"key": "group_id", "match": {"value": TENANT}}]},
        "limit": 3,
        "with_payload": True,
    }
    assert [passage.id for passage in found] == [
        "A made-up guide/chunk_003",
        "A made-up guide/chunk_007",
    ]
    first = found[0]
    assert (first.title, first.text, first.score, first.source) == (
        "Archiving a made-up item",
        SOURCE_TEXT,
        0.71,
        "A made-up guide",
    )
    assert first.steps == ("Open the made-up item.", "Press Archive.")


@pytest.mark.parametrize("limit", [1, 5, 20])
def test_the_tenants_filter_is_never_left_out(limit: int) -> None:
    service = Service()
    kb, _ = adapter(service)
    _search(kb, limit=limit)
    [query] = service.at(QUERY)
    assert body(query)["filter"] == {"must": [{"key": "group_id", "match": {"value": TENANT}}]}
    assert body(query)["limit"] == limit


def test_the_session_cookie_goes_to_qdrant_alone() -> None:
    """The gateway's session goes to Qdrant as one header, and to no other service; no cookie
    a response sets (the gateway's own, the embedding service's) is kept or sent."""
    service = Service()
    kb, _ = adapter(service)

    async def two() -> None:
        for _ in range(2):
            await kb.search(QUESTION, language="en", caller=CALLER, limit=2)
        await kb.aclose()

    asyncio.run(two())
    assert service.signed_in == ["made-up-session-1"]  # one sign-in serves both searches
    for request in [*service.at(LOGIN), *service.at(EMBED)]:
        assert "cookie" not in request.headers
    queries = service.at(QUERY)
    assert len(queries) == 2
    assert all(q.headers.get_list("cookie") == ["ole5_session=made-up-session-1"] for q in queries)


def test_a_refused_session_signs_in_again_once_and_asks_once_more() -> None:
    service = Service()
    kb, _ = adapter(service)

    async def scene() -> list[Passage]:
        await kb.search(QUESTION, language="en", caller=CALLER, limit=2)
        service.accepted = {"made-up-session-2"}  # the first session ends
        try:
            return await kb.search(QUESTION, language="en", caller=CALLER, limit=2)
        finally:
            await kb.aclose()

    found = asyncio.run(scene())
    assert len(found) == 2
    assert service.signed_in == ["made-up-session-1", "made-up-session-2"]
    cookies = [q.headers["cookie"] for q in service.at(QUERY)]
    assert cookies == [
        "ole5_session=made-up-session-1",
        "ole5_session=made-up-session-1",
        "ole5_session=made-up-session-2",
    ]


def test_a_session_refused_again_is_a_rejected_request_after_one_more_sign_in() -> None:
    service = Service()
    service.accepted = set()  # Qdrant refuses every session
    kb, _ = adapter(service)
    with pytest.raises(ProviderError) as refused:
        _search(kb)
    assert (refused.value.kind, refused.value.retryable) == ("rejected", False)
    assert refused.value.details == {"step": "search", "error": "status", "status": 401}
    assert len(service.signed_in) == 2 and len(service.at(QUERY)) == 2


def test_searches_refused_together_sign_in_again_once() -> None:
    """Two searches whose session Qdrant refuses at once sign in again once, under the lock:
    the second takes the session the first signed in."""
    service = Service(sessions=("made-up-session-1", "made-up-session-2", "made-up-session-3"))
    kb, _ = adapter(service)

    async def scene() -> list[list[Passage]]:
        await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        service.accepted = {"made-up-session-2"}  # the first session ends
        try:
            return list(
                await asyncio.gather(
                    *(kb.search(QUESTION, language="en", caller=CALLER, limit=1) for _ in "ab")
                )
            )
        finally:
            await kb.aclose()

    found = asyncio.run(scene())
    assert [len(each) for each in found] == [1, 1]
    assert service.signed_in == ["made-up-session-1", "made-up-session-2"]


def test_searches_started_together_sign_in_once() -> None:
    service = Service()
    kb, _ = adapter(service)

    async def scene() -> None:
        questions = (kb.search(QUESTION, language="en", caller=CALLER, limit=1) for _ in "abc")
        await asyncio.gather(*questions)
        await kb.aclose()

    asyncio.run(scene())
    assert service.signed_in == ["made-up-session-1"]


def test_one_client_stays_open_between_searches_and_aclose_closes_it() -> None:
    service = Service()
    kb, transport = adapter(service)

    async def scene() -> ProviderError:
        await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        assert transport.closed == 0  # kept open between the two
        await kb.aclose()
        with pytest.raises(ProviderError) as closed:
            await kb.search(QUESTION, language="en", caller=CALLER, limit=1)
        return closed.value

    closed = asyncio.run(scene())
    assert transport.closed == 1
    assert len(service.requests) == 5  # one sign-in, two embeddings, two searches
    assert (closed.kind, closed.details) == ("server_error", {"step": "embed", "error": "closed"})


def test_the_connections_and_timeouts_suit_a_tool() -> None:
    """Connections are kept open five minutes (the prototype's D41), and a whole search ends
    before the knowledge tool's own timeout would cut it."""
    assert LIMITS.keepalive_expiry == 300.0
    assert (TIMEOUT.connect, TIMEOUT.read) == (2.0, 3.0)
    assert Tool.model_fields["timeout_s"].default > DEADLINE_S
    assert DIMENSIONS == 1024


def test_a_search_gives_at_most_its_limit_whatever_the_answer_holds() -> None:
    service = Service()  # it answers two points to every query
    kb, _ = adapter(service)
    assert [passage.id for passage in _search(kb, limit=1)] == ["A made-up guide/chunk_003"]


def test_a_question_with_no_words_is_not_sent_and_a_limit_under_one_is_refused() -> None:
    service = Service()
    kb, _ = adapter(service)
    assert _search(kb, "   ") == []
    assert service.requests == []
    kb, _ = adapter(service)
    with pytest.raises(ValueError, match="at least one passage"):
        _search(kb, limit=0)


def test_a_point_that_cannot_be_read_is_left_out(caplog: pytest.LogCaptureFixture) -> None:
    service = Service()
    unreadable: list[dict[str, Any]] = [
        {"id": 1, "score": 0.9, "payload": {"metadata": {"chunk_id": "chunk_001"}}},
        {"id": 2, "score": "high", "payload": service.points[0]["payload"]},
    ]
    service.points = [*unreadable, *service.points]
    kb, _ = adapter(service)
    caplog.set_level("WARNING")
    found = _search(kb)
    assert [passage.id for passage in found] == [
        "A made-up guide/chunk_003",
        "A made-up guide/chunk_007",
    ]
    [record] = [r for r in caplog.records if r.getMessage() == "knowledge_points_skipped"]
    assert vars(record)["fields"] == {"skipped": 2}


def test_a_cancelled_search_stops_at_once() -> None:
    """A cancel is never caught: the search stops while its request waits, with no error of
    its own."""
    service = Service()
    waiting = asyncio.Event()

    async def never(request: httpx.Request) -> httpx.Response:
        waiting.set()
        await asyncio.Event().wait()
        raise AssertionError("never answered")

    service.replace(EMBED, never)
    kb, _ = adapter(service)

    async def scene() -> None:
        task = asyncio.create_task(kb.search(QUESTION, language="en", caller=CALLER, limit=1))
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)
        await kb.aclose()

    asyncio.run(scene())
