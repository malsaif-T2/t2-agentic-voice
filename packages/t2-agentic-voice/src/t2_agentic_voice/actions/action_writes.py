"""How an action's write, its lookup and its `validate` are called (the design's 6.4;
docs/SECURITY.md, invariant 6), for actions/action_runner.py: the team's function, a sync one in a
worker thread, within the action's `timeout_s` on the call's clock, and what came back read as
one of the error meanings.

- **`Returned(result)`**: the write returned a value its result model parses.
- **`Refused(state)`**: `ActionRejected` (`rejected`) or `ActionNotSent` (`not_sent`):
  definitely not done.
- **`Lost(note)`**: the write timed out (`timed_out`), raised anything else (`raised`), or gave
  something its result model refuses (`unreadable_result`): it may or may not have been done,
  so the runner looks it up by its request ID.

A write still running at its timeout is never cancelled, so a write is never cut in half: it
runs to its end, kept alive here, its outcome discarded and its end logged. A lookup or a
`validate` still running at its timeout is cancelled, since each only reads. Every log line
names the action and the kind of failure, never a value, a reason or an exception's text.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from t2_agentic_voice.actions.action import Action, ActionContext
from t2_agentic_voice.actions.runner import called, frames_of, within
from t2_agentic_voice.actions.signature import context_parameter
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.errors import ActionNotSent, ActionRejected, ToolError
from t2_agentic_voice.core.logging import get_logger

_log = get_logger(__name__)
# The writes left running past their timeout, held so none is collected before it ends.
_LATE: set[asyncio.Future[Any]] = set()


@dataclass(frozen=True, slots=True)
class Returned:
    """The write returned `result`."""

    result: BaseModel


@dataclass(frozen=True, slots=True)
class Refused:
    """The write was definitely not done: the outbox row's `state`."""

    state: Literal["rejected", "not_sent"]


@dataclass(frozen=True, slots=True)
class Lost:
    """No reply that says how the write ended: `note`, the outbox row's word for why."""

    note: Literal["timed_out", "raised", "unreadable_result"]


type Written = Returned | Refused | Lost


def parsed_result(model: type[BaseModel], value: object) -> BaseModel | None:
    """`value` as `model`, None when `model` refuses it."""
    if isinstance(value, model):
        return value
    try:
        return model.model_validate(value)
    except ValidationError:
        return None


def _ended_late(action: str, work: asyncio.Future[Any]) -> None:
    """A write left running past its timeout ended: its outcome is discarded, its end logged."""
    _LATE.discard(work)
    failure = None
    if work.cancelled():
        failure = "CancelledError"
    elif (error := work.exception()) is not None:
        failure = type(error).__qualname__
    _log.info("action_replied_late", action=action, failure=failure)


async def write(action: Action, ctx: ActionContext, draft: BaseModel, clock: Clock) -> Written:
    """Run `action`'s write of `draft` (the module's docstring)."""
    kwargs: dict[str, Any] = {"draft": draft}
    own = context_parameter(action.execute, context=ActionContext)
    if own is not None:
        kwargs[own] = ctx
    work = asyncio.ensure_future(called(action.execute, **kwargs))
    if not await within(work, action.timeout_s, clock):
        _LATE.add(work)
        work.add_done_callback(functools.partial(_ended_late, action.name))
        _log.warning("action_timed_out", action=action.name, timeout_s=action.timeout_s)
        return Lost("timed_out")
    if work.cancelled():
        return Lost("raised")
    error = work.exception()
    if isinstance(error, ActionRejected):
        _log.info("action_rejected", action=action.name)
        return Refused("rejected")
    if isinstance(error, ActionNotSent):
        _log.info("action_not_sent", action=action.name)
        return Refused("not_sent")
    if error is not None:
        failure = type(error).__qualname__
        _log.error("action_failed", action=action.name, failure=failure, at=frames_of(error))
        return Lost("raised")
    result = parsed_result(action.result, work.result())
    if result is None:
        _log.error("action_result_unreadable", action=action.name)
        return Lost("unreadable_result")
    return Returned(result)


async def _read(
    name: str, step: str, call: Coroutine[Any, Any, Any], seconds: float, clock: Clock
) -> tuple[bool, Any]:
    """`call`, a read, run within `seconds` and cancelled past them: whether it gave a value,
    and the value."""
    work = asyncio.ensure_future(call)
    try:
        ended = await within(work, seconds, clock)
    finally:
        if not work.done():
            work.cancel()
    if not ended or work.cancelled():
        _log.warning(f"action_{step}_timed_out", action=name, timeout_s=seconds)
        return False, None
    error = work.exception()
    if error is not None:
        failure = type(error).__qualname__
        _log.error(f"action_{step}_failed", action=name, failure=failure, at=frames_of(error))
        return False, None
    return True, work.result()


async def look_up(action: Action, ctx: ActionContext, clock: Clock) -> BaseModel | None:
    """The result of the write `ctx.request_id` as the action's lookup finds it; None when it
    has no lookup, finds nothing, fails, times out or gives what the result model refuses."""
    finder = action.finder
    if finder is None:
        return None
    call = called(finder, ctx, ctx.request_id)
    gave, value = await _read(action.name, "lookup", call, action.timeout_s, clock)
    if not gave or value is None:
        return None
    found = parsed_result(action.result, value)
    if found is None:
        _log.error("action_lookup_unreadable", action=action.name)
    return found


async def validated(
    action: Action, ctx: CallContext, draft: BaseModel, clock: Clock
) -> tuple[bool, Any]:
    """`action`'s `validate(ctx, draft)`, run as a read: whether it gave a value, and the value
    (the draft it kept, None for the draft as it was, or the `ToolError` it raised, which the
    talker is told)."""
    validate = action.validate
    if validate is None:
        return True, None
    work = _kept_tool_error(called(validate, ctx, draft))
    return await _read(action.name, "validate", work, action.timeout_s, clock)


async def _kept_tool_error(work: Coroutine[Any, Any, Any]) -> Any:
    """`work`'s value, or the `ToolError` it raised as a value."""
    try:
        return await work
    except ToolError as error:
        return error
