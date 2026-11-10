"""The faults `ActionSafetySuite` gives a team's action (testing/action_safety.py; the design's 9.3
and 6.4), each through `Action.replaced`, so the action under test keeps its name, its draft and
its words and only its write and its lookup change.

`Writes` watches one action's writes: each call of the function counted (`made`), the team's
own write run as the action would run it (its context found by its type, a sync one called
directly), and each result kept by its request ID, so a lookup can find a write whose reply was
lost. The faults: the write counted (`counted`); done but its reply lost (`lost`); never
answered (`hangs`); refused (`refused`, with `ActionRejected` or `ActionNotSent`); and the
lookups, one that finds what was written (`found`) and one that finds nothing (`nothing`).
A fault hangs on an event that never comes, so only the runner's timeout, on the call's clock,
ends it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from t2_agentic_voice.actions.action import Action, ActionContext
from t2_agentic_voice.actions.signature import context_parameter, is_async
from t2_agentic_voice.core.errors import ActionNotSent, ActionRejected


class Writes:
    """The writes of `action` (the module's docstring)."""

    def __init__(self, action: Action) -> None:
        self.action = action
        self.made = 0
        self.results: dict[str, Any] = {}
        self._context = context_parameter(action.execute, context=ActionContext)
        self._async = is_async(action.execute)

    async def write(self, ctx: ActionContext, draft: BaseModel) -> Any:
        """The team's own write of `draft`, counted, its result kept by `ctx.request_id`."""
        self.made += 1
        given: dict[str, Any] = {"draft": draft}
        if self._context is not None:
            given[self._context] = ctx
        result = await self.action.execute(**given) if self._async else self.action.execute(**given)
        self.results[ctx.request_id] = result
        return result

    def counted(self) -> Action:
        """The action, each write counted."""
        return self.action.replaced(execute=self.write)

    def lost(self, *, lookup: bool) -> Action:
        """The action whose write is done but its reply lost, with a lookup that finds it, or
        one that finds nothing (`lookup` False)."""

        async def lost(ctx: ActionContext, draft: BaseModel) -> Any:
            await self.write(ctx, draft)
            await _never()

        return self.action.replaced(execute=lost, lookup=self.found if lookup else nothing)

    def hangs(self) -> Action:
        """The action whose backend never answers, nothing written, and nothing found."""

        async def hangs(ctx: ActionContext, draft: BaseModel) -> Any:
            self.made += 1
            await _never()

        return self.action.replaced(execute=hangs, lookup=nothing)

    def refused(self, error: type[ActionRejected | ActionNotSent]) -> Action:
        """The action whose write is definitely not done: it raises `error`."""

        async def refused(ctx: ActionContext, draft: BaseModel) -> Any:
            self.made += 1
            raise error("refused by the suite's fault")

        return self.action.replaced(execute=refused, lookup=nothing)

    async def found(self, ctx: ActionContext, request_id: str) -> Any:
        """The lookup that finds what was written for `request_id`, None for nothing."""
        return self.results.get(request_id)


async def nothing(ctx: ActionContext, request_id: str) -> None:
    """The lookup that finds nothing."""
    return None


async def _never() -> None:
    """Wait for what never comes, until cancelled."""
    await asyncio.Event().wait()
