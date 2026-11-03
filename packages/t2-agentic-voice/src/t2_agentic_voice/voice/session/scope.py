"""Each reply's cancel scope (the design's 6.4; plan 005): the work that answers one of the
caller's turns starts inside it, whatever that work is (the echo's, the talker's model stream and
read-only lookups, or a team's agent in the agent-led mode, D-050), so a stop cancels at once
everything working for that reply: every task of the scope is cancelled, then awaited for at most
`wait_s` on the call's clock. A task that honours its cancellation has ended by then, so none is
left; one that does not end within `wait_s` (it suppresses its cancellation, or waits on a worker
thread, which cannot be cancelled) is logged by its name alone and left to end on its own, the
scope still holding it (`running` counts it) and reading its outcome when it ends, so it is never
collected mid-run nor ends with an error unread. Work started outside a scope (an action's write,
which runs as a job of `actions`, the design's 6.4) is never cancelled by one.

The session opens one for each reply it asks for (speaker.py) and cancels it when the reply ends,
however: played, stopped, or cut by the call's end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.session.io import Clock

_log = get_logger(__name__)

# How long a stop waits, on the call's clock, for the tasks it cancelled to end (the agent's
# bound, plan 005's 100 ms); what is still running then is left to end on its own (the module's
# docstring).
CANCEL_WAIT_S = 0.1


async def _refused[T]() -> T:
    """What a scope already cancelled runs instead of its work: a task that ends cancelled."""
    raise asyncio.CancelledError


class CancelScope:
    """One reply's work: each task started in it (`start`), all cancelled at once and awaited
    (`cancel`), within `wait_s` on `clock`; `name` names it, and each of its tasks, in logs."""

    def __init__(self, *, name: str, clock: Clock, wait_s: float = CANCEL_WAIT_S) -> None:
        self.name = name
        self._clock = clock
        self._wait_s = wait_s
        self._tasks: set[asyncio.Task[Any]] = set()
        self._cancelled = False

    def start[T](self, work: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
        """Run `work` as a task of this scope, named `name`; a scope already cancelled starts
        none (the coroutine is closed, and the task returned is cancelled)."""
        if self._cancelled:
            work.close()
            return asyncio.create_task(_refused(), name=name)
        task = asyncio.create_task(work, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._ended)
        return task

    async def cancel(self) -> None:
        """Cancel every task of the scope at once, then await them, at most `wait_s` on the
        call's clock; once cancelled, the scope starts nothing more. A task of the scope that
        asks for it is not awaited by itself. Never raises."""
        self._cancelled = True
        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current and not task.done()]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        ended = asyncio.create_task(asyncio.wait(tasks), name=f"{self.name}-cancel")
        timer = asyncio.create_task(self._clock.sleep(self._wait_s), name=f"{self.name}-bound")
        try:
            await asyncio.wait((ended, timer), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in (ended, timer):
                waiter.cancel()
            await asyncio.wait((ended, timer))
        left = sorted(task.get_name() for task in tasks if not task.done())
        if left:
            _log.warning("scope_tasks_left", scope=self.name, tasks=left)

    @property
    def cancelled(self) -> bool:
        """Whether `cancel` has been asked."""
        return self._cancelled

    @property
    def running(self) -> int:
        """How many of the scope's tasks have not ended."""
        return sum(not task.done() for task in self._tasks)

    def _ended(self, task: asyncio.Task[Any]) -> None:
        """A task of the scope ended: it is let go, and a failure other than its cancellation
        is logged by its kind alone, so no error is left unread."""
        self._tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            failure = type(error).__qualname__
            _log.warning(
                "scope_task_failed", scope=self.name, task=task.get_name(), failure=failure
            )
