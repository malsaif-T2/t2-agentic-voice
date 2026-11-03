"""Each reply's cancel scope (voice/session/scope.py): built with its name, its clock and its
bound, and a stub until plan 005's Track B builds it, whose tests drive it with the slow
responder (tests/t2_agentic_voice/responder_fakes.py) on the fake clock."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.voice.session.scope import CANCEL_WAIT_S, CancelScope

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.responder_fakes import SlowResponder


def test_the_scope_is_a_stub_until_it_is_built() -> None:
    clock = FakeClock()
    scope = CancelScope(name="reply-1", clock=clock)
    assert (scope.name, CANCEL_WAIT_S) == ("reply-1", 0.1)

    async def call() -> None:
        work = SlowResponder(clock).read()
        with pytest.raises(NotImplementedError, match="Track B"):
            scope.start(work, name="model")
        work.close()
        with pytest.raises(NotImplementedError, match="Track B"):
            await scope.cancel()

    asyncio.run(call())
    with pytest.raises(NotImplementedError, match="Track B"):
        _ = scope.cancelled
    with pytest.raises(NotImplementedError, match="Track B"):
        _ = scope.running
