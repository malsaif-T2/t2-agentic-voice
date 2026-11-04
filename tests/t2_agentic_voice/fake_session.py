"""A fake of the session (voice/session/io.py's `Session`) for the Pipecat side's tests, beside the
fakes of the session's other side in session_fakes.py; tests/t2_agentic_voice/test_session_fakes.py
checks it.

`FakeSession` takes one lock for each step, as `CallSession` does, and holds it while it awaits
`Commands.run`, so a `run` that breaks io.py's rule (it returns once the command is queued, and
never calls the session back: TD-068) fails in a test rather than hanging a call: a `run` that
calls `handle`, `aclose` or `give` from inside is a RuntimeError at once, and one that does not
return within `run_s` (waiting on the pipeline, on playback or on the peer's close) is one too.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Sequence

from t2_agentic_voice.voice.session.commands import Command
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.session_events import SessionEvent

# The longest a `Commands.run` may take before the fake session fails it (the agent's bound):
# queueing a command takes milliseconds, and this leaves room for a slow machine's stalls.
RUN_S = 5.0


class FakeSession:
    """A session (`Session`) for the Pipecat side's tests, built as `CallSession` is, from a
    call's setup and where its commands go: it keeps every event handed to it, and for each
    gives the commands `replies` returns for it, in order (none by default); `closed` says
    whether its stream has ended (`aclose`). A test gives a command of its own with `give`.
    Each step holds the session's lock, as the module's docstring says."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        *,
        replies: Callable[[SessionEvent], Sequence[Command]] = lambda event: (),
        run_s: float = RUN_S,
    ) -> None:
        self.setup = setup
        self.commands = commands
        self.replies = replies
        self.run_s = run_s
        self.events: list[SessionEvent] = []
        self.closed = False
        self._lock = asyncio.Lock()
        self._holder: asyncio.Task[object] | None = None

    async def handle(self, event: SessionEvent) -> None:
        async with self._step("handle"):
            self.events.append(event)
            for command in self.replies(event):
                await self._run(command)

    async def aclose(self) -> None:
        async with self._step("aclose"):
            self.closed = True

    async def give(self, command: Command) -> None:
        async with self._step("give"):
            await self._run(command)

    @contextlib.asynccontextmanager
    async def _step(self, name: str) -> AsyncIterator[None]:
        """One step, under the session's lock; RuntimeError for a step a `Commands.run` asked
        for while the session held it, which in a call would never return."""
        if self._holder is not None and self._holder is asyncio.current_task():
            raise RuntimeError(
                f"Commands.run called the session's {name} while the session awaited it "
                "(io.py, TD-068). FIX: hand what the command brings about as an event, later, "
                "never from inside `run`."
            )
        async with self._lock:
            self._holder = asyncio.current_task()
            try:
                yield
            finally:
                self._holder = None

    async def _run(self, command: Command) -> None:
        try:
            async with asyncio.timeout(self.run_s):
                await self.commands.run(command)
        except TimeoutError:
            raise RuntimeError(
                f"Commands.run did not return within {self.run_s} s for "
                f"{type(command).__name__} (io.py, TD-068). FIX: return once the command is "
                "queued, never waiting on the pipeline, on playback or on the peer's close."
            ) from None
