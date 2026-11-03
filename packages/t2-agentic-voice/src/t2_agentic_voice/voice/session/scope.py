"""Each reply's cancel scope (the design's 6.4; plan 005): the work that answers one of the
caller's turns starts inside it, whatever that work is (the echo's, the talker's model stream and
read-only lookups, or a team's agent in the agent-led mode, D-050), so a stop cancels at once
everything working for that reply: every task of the scope is cancelled and awaited, for at
most `wait_s` on the call's clock, and none is left. Work started outside a scope (an
action's write, which runs as a job of `actions`, the design's 6.4) is never cancelled by one.

Plan 005's Track B builds it; until then each method but the constructor raises.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from t2_agentic_voice.voice.session.io import Clock

# How long a stop waits, on the call's clock, for the tasks it cancelled to end (the agent's
# bound, plan 005's 100 ms): a task that has not ended by then (a lookup in a worker thread,
# which cannot be cancelled) is left to end on its own, and logged by its name alone.
CANCEL_WAIT_S = 0.1


class CancelScope:
    """One reply's work: each task started in it (`start`), all cancelled at once and awaited
    (`cancel`), within `wait_s` on `clock`; `name` names it, and each of its tasks, in logs."""

    def __init__(self, *, name: str, clock: Clock, wait_s: float = CANCEL_WAIT_S) -> None:
        self.name = name
        self._clock = clock
        self._wait_s = wait_s

    def start[T](self, work: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
        """Run `work` as a task of this scope, named `name`; a scope already cancelled starts
        none (the coroutine is closed, and the task returned is cancelled)."""
        raise NotImplementedError("the cancel scope is plan 005's Track B's to build")

    async def cancel(self) -> None:
        """Cancel every task of the scope at once, then await them, at most `wait_s` on the
        call's clock; once cancelled, the scope starts nothing more. Never raises."""
        raise NotImplementedError("the cancel scope is plan 005's Track B's to build")

    @property
    def cancelled(self) -> bool:
        """Whether `cancel` has been asked."""
        raise NotImplementedError("the cancel scope is plan 005's Track B's to build")

    @property
    def running(self) -> int:
        """How many of the scope's tasks have not ended."""
        raise NotImplementedError("the cancel scope is plan 005's Track B's to build")
