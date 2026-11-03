"""The work that answers a caller's turn, slowed, for the cancel scope's tests
(voice/session/scope.py): a reply's model stream and a read-only lookup, as a talker will run
them, each sleeping on the fake clock (fakes.py's `FakeClock`) so a test holds them mid-flight,
stops the reply, and checks that both were cancelled within the scope's bound and that no task
of the call is left; tests/t2_agentic_voice/test_session_fakes.py checks it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence

from tests.t2_agentic_voice.fakes import FakeClock

# What the slow model says, a chunk at a time.
CHUNKS = ("made-up", "reply", "words")


class SlowResponder:
    """A reply's slow work: `stream`, the model's text, one of `chunks` every `chunk_s`
    (`read` takes it whole); and `lookup`, a read-only lookup that answers after `lookup_s`.
    Each keeps, by its name (`stream`, `lookup`), when it started and when it finished or was
    cancelled, on the clock (`started`, `finished`, `cancelled`)."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        chunks: Sequence[str] = CHUNKS,
        chunk_s: float = 1.0,
        lookup_s: float = 5.0,
    ) -> None:
        self.clock = clock
        self.chunks = tuple(chunks)
        self.chunk_s = chunk_s
        self.lookup_s = lookup_s
        self.started: dict[str, float] = {}
        self.finished: dict[str, float] = {}
        self.cancelled: dict[str, float] = {}

    async def stream(self) -> AsyncIterator[str]:
        async with self._watched("stream"):
            for chunk in self.chunks:
                await self.clock.sleep(self.chunk_s)
                yield chunk

    async def read(self) -> str:
        """The model's whole text, read from its stream."""
        return " ".join([chunk async for chunk in self.stream()])

    async def lookup(self, query: str) -> str:
        """What a lookup for `query` found, after `lookup_s`."""
        async with self._watched("lookup"):
            await self.clock.sleep(self.lookup_s)
            return f"found for {query}"

    @contextlib.asynccontextmanager
    async def _watched(self, name: str) -> AsyncIterator[None]:
        self.started[name] = self.clock.now()
        try:
            yield
        except asyncio.CancelledError:
            self.cancelled[name] = self.clock.now()
            raise
        self.finished[name] = self.clock.now()
