"""The actions of a runtime's agent, composed (plan 007, Track B; the design's 6.4 and 10.6): the
composition root's part, since only api may build an adapter (harness.toml [layers]).

- **`open_actions`**, in the runtime's lifespan: for an agent that declares actions, one
  `ActionRunner` for every call of the runtime, on the SQLite outbox at `outbox_path`
  (`storage.var_dir/<agent name>/outbox.sqlite3`), the per-caller cap from
  `limits.actions_per_caller_per_day`; the rows an earlier process left `sending` reconciled
  before any call starts (invariant 6); the outbox closed as the lifespan ends. An agent with
  no actions opens no outbox: None. The runner emits no event: the session reports each
  outcome (`ActionCompleted`, `ActionUnconfirmed`) from the `ActionOutcome` it is returned,
  as `voice` builds the events (core/events.py), so an observer hears each outcome once.
- **What `t2v outbox` reads** (api/cli.py prints it): the rows (`outbox_rows`, none for an
  outbox not made yet, which reading never makes), each as `shown_row` gives it, and
  `reconciled`, which takes the runtime's lock first, so it never runs beside a server on the
  same `storage.var_dir`, then looks the rows left `sending` and the flagged ones up again,
  never sending one again.

**What a row shows** a person who reconciles: its request ID, the call's ID, the action, where
it stands, the note of why (a fixed word or two, never a value), its times, and whether it
holds a result. Never the draft, the result or the caller's subject, which are call content and
the caller's identity (docs/SECURITY.md, invariant 8): the request ID is the key a backend's own
records are searched by.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Final

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.api.lockfile import LockFile
from t2_agentic_voice.api.providers import actions_of
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import NotFoundError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry, OutboxState

# The outbox's file under the agent's folder of `storage.var_dir`.
OUTBOX_NAME: Final = "outbox.sqlite3"
# What `show` says of a request ID the outbox does not hold, never the ID itself.
NO_ROW = "The outbox holds no row of that request ID. FIX: copy it from `t2v outbox list APP`."

log = get_logger(__name__)


def outbox_path(settings: VoiceSettings, agent: VoiceAgent) -> Path:
    """Where `agent`'s outbox is kept: its folder of `storage.var_dir`."""
    return settings.storage.var_dir / agent.name / OUTBOX_NAME


def _runner(agent: VoiceAgent, settings: VoiceSettings, outbox: Outbox) -> ActionRunner:
    """The runner, with no `emit`: the session reports each outcome's event (the module's
    docstring)."""
    return ActionRunner(
        actions_of(agent),
        outbox=outbox,
        per_caller_per_day=settings.limits.actions_per_caller_per_day,
    )


async def open_actions(
    agent: VoiceAgent, settings: VoiceSettings, *, clock: Clock, stack: AsyncExitStack
) -> ActionRunner | None:
    """The agent's one action runner (the module's docstring), its outbox's close pushed on
    `stack`; None for an agent with no actions."""
    from t2_agentic_voice.adapters.outbox import SqliteOutbox

    if not actions_of(agent):
        return None
    outbox = await SqliteOutbox.open(outbox_path(settings, agent))
    stack.push_async_callback(outbox.aclose)
    runner = _runner(agent, settings, outbox)
    reconciled = await runner.reconcile(clock=clock)
    log.info("actions_opened", actions=len(runner.actions), reconciled=reconciled)
    return runner


async def outbox_rows(
    settings: VoiceSettings, agent: VoiceAgent, *, state: OutboxState | None = None
) -> tuple[OutboxEntry, ...]:
    """The outbox's rows, oldest first, of `state` when given; none when no outbox was made
    yet, which reading never makes."""
    from t2_agentic_voice.adapters.outbox import SqliteOutbox

    path = outbox_path(settings, agent)
    if not path.is_file():
        return ()
    outbox = await SqliteOutbox.open(path)
    try:
        return await outbox.entries(state=state)
    finally:
        await outbox.aclose()


async def outbox_row(settings: VoiceSettings, agent: VoiceAgent, request_id: str) -> OutboxEntry:
    """The row `request_id`; NotFoundError, naming no ID, when the outbox holds none."""
    from t2_agentic_voice.adapters.outbox import SqliteOutbox

    path, row = outbox_path(settings, agent), None
    if path.is_file():
        outbox = await SqliteOutbox.open(path)
        try:
            row = await outbox.get(request_id)
        finally:
            await outbox.aclose()
    if row is None:
        raise NotFoundError(NO_ROW)
    return row


async def reconciled(
    settings: VoiceSettings, agent: VoiceAgent, *, clock: Clock = SYSTEM_CLOCK
) -> int:
    """Look up the rows left `sending` and the flagged ones again, under the runtime's lock
    (a ConfigurationError while a server holds it); how many rows were looked at."""
    from t2_agentic_voice.adapters.outbox import SqliteOutbox

    path = outbox_path(settings, agent)
    if not actions_of(agent) or not path.is_file():
        return 0
    lock = LockFile.take(settings.storage.var_dir)
    try:
        outbox = await SqliteOutbox.open(path)
        try:
            return await _runner(agent, settings, outbox).reconcile(clock=clock, flagged=True)
        finally:
            await outbox.aclose()
    finally:
        lock.release()


def shown_row(row: OutboxEntry) -> dict[str, str | bool | None]:
    """What a row shows a person (the module's docstring), as JSON values."""
    return {
        "request_id": row.request_id,
        "call_id": row.call_id,
        "action": row.action,
        "state": row.state,
        "note": row.note,
        "created_at": row.created_at.isoformat(timespec="seconds"),
        "updated_at": row.updated_at.isoformat(timespec="seconds"),
        "holds_result": row.result_json is not None,
    }
