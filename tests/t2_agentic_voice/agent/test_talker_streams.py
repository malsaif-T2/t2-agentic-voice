"""The model's stream as the talker reads it (agent/turn.py; plan 006): closed with the reply by
`contextlib.aclosing`, at once, when its reader stops mid-stream; read whole when it is an async
iterator but no generator; and a `ScriptedLLM` whose script ran out failing the test, never
read as the model's failure."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

import pytest
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest, Done, TextDelta
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM, ScriptExhaustedError
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.t2_agentic_voice.agent.chat_support import HOLD, FakeChat, kinds, reply, talker

TURN = TalkerTurn(turn_id=1, words="How do I reset my password?", language="en")


def test_a_script_that_ran_out_fails_the_test_never_as_a_models_failure() -> None:
    """`ScriptExhaustedError`, an AssertionError, comes out of the reply as it is, never as a
    `ProviderError`, so nothing says the `error` notice for it."""
    model = ScriptedLLM([ScriptedLLM.reply("Sure.")])
    chat = talker(model)
    model.clock = chat.clock
    reply(chat, TURN)
    with pytest.raises(ScriptExhaustedError, match="request 2 came after its last"):
        reply(chat, TalkerTurn(turn_id=2, words="and then?"))


def test_a_reply_closed_mid_stream_closes_the_models_stream_at_once() -> None:
    """A reply its reader stops at a clause closes the model's stream when it is closed
    (`contextlib.aclosing`), not when it is collected."""
    model = FakeChat([TextDelta(text="Open the portal. "), HOLD, TextDelta(text="Never said.")])
    chat = talker(model)

    async def run() -> None:
        scope = CancelScope(name="reply-1", clock=chat.clock)
        events = cast(AsyncGenerator[TalkerEvent, None], chat.reply(TURN, scope=scope))
        async for event in events:
            if isinstance(event, SpokenClause):
                break
        assert model.closed == 0
        await events.aclose()
        assert model.closed == 1

    asyncio.run(run())


class _PlainStream:
    """A model's stream that is an async iterator but no generator, with nothing to close."""

    def __init__(self, *events: ChatEvent) -> None:
        self.events = list(events)

    def __aiter__(self) -> _PlainStream:
        return self

    async def __anext__(self) -> ChatEvent:
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)


class _PlainChat(FakeChat):
    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        return _PlainStream(TextDelta(text="Sure."), Done(finish_reason="stop"))


def test_a_stream_that_is_no_generator_is_read_whole() -> None:
    events = reply(talker(_PlainChat()), TURN)
    assert kinds(events)[-3:] == ["SpokenClause", "ModelReplied", "ReplyDone"]
