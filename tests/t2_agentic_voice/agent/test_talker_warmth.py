"""Each talker request's warm flag (agent/turn_answer.py, the `ConnectionWarmth` port): whether
the request went out on a kept-alive connection, read from the chat model just before it went
and carried on its `ModelReplied` (`warm_connection`), the turn's first's on its `talker_replied`
line; None from a chat model that does not say.
A fake chat model keeps its connection as GroqChat does: warm after a stream read to its end,
cold before any and after a cancelled one."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import ModelReplied, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.connection_warmth import ConnectionWarmth, warm_now
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.t2_agentic_voice.agent.chat_support import (
    HOLD,
    FakeChat,
    call,
    calls,
    reply,
    said,
    settle,
    talker,
)
from tests.t2_agentic_voice.fakes import FakeClock


class _KeptChat(FakeChat):
    """A `FakeChat` that keeps its connection as GroqChat does (the module's docstring)."""

    def __init__(self, *entries: Any) -> None:
        super().__init__(*entries)
        self.kept = False

    def warm(self) -> bool:
        return self.kept

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        ended = False
        try:
            async for event in super().stream(request):
                yield event
            ended = True
        finally:
            self.kept = ended


def _flags(events: list[TalkerEvent]) -> list[bool | None]:
    return [e.warm_connection for e in events if isinstance(e, ModelReplied)]


def _turn(turn_id: int) -> TalkerTurn:
    return TalkerTurn(turn_id=turn_id, words="How do I reset my password?", language="en")


def test_a_cold_request_then_a_warm_one_then_one_after_a_cancel_each_carry_their_flag() -> None:
    model = _KeptChat(said("Open the portal."), said("Then reset it."), [HOLD], said("Done."))
    assert isinstance(model, ConnectionWarmth)
    chat = talker(model, clock=FakeClock())
    assert _flags(reply(chat, _turn(1))) == [False]  # the first request opens its connection
    assert _flags(reply(chat, _turn(2))) == [True]  # the next goes out on the one kept

    async def cancel(task: Any, events: list[TalkerEvent], scope: CancelScope, _: Any) -> None:
        await settle()
        await scope.cancel()  # a barge-in: the stream is cut and its connection closed

    assert _flags(reply(chat, _turn(3), steps=cancel)) == []
    assert not model.kept
    assert _flags(reply(chat, _turn(4))) == [False]  # after the cancel it went out cold
    assert len(model.requests) == 4


def test_a_chat_model_that_does_not_say_gives_no_flag() -> None:
    model = FakeChat(said("Open the portal."))
    assert warm_now(model) is None
    assert _flags(reply(talker(model), _turn(1))) == [None]


def test_the_flag_is_read_from_a_model_that_says() -> None:
    model = _KeptChat()
    assert warm_now(model) is False
    model.kept = True
    assert warm_now(model) is True
    asyncio.run(model.aclose())


@tool(description="Read a made-up page.")
async def read_page() -> dict[str, str]:
    return {"title": "Made up"}


def test_the_turns_line_says_its_first_requests_flag(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    model = _KeptChat(calls(call("read_page")), said("Open the portal."))
    events = reply(talker(model, read_page), _turn(1))
    assert _flags(events) == [False, True]  # the tool's round trip went out on the one kept
    (line,) = [r for r in caplog.records if r.getMessage() == "talker_replied"]
    assert getattr(line, FIELDS)["warm_connection"] is False
