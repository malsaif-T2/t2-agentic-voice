"""A confirmed action's write in the call (plan 007; the design's 6.4; docs/SECURITY.md, invariant
6), for voice/session/yes_turns.py.

- **The job.** The `ConfirmedAction` the yes rule issued goes to the call's `ActionJobs`
  (`CallSetup.action_jobs`: the port the api layer fills with the action runner, one for every
  call, each told apart by its `call_id`) as a task of its own, outside every reply's cancel
  scope and off the session's lock, so neither a stop nor the call's end cuts it in half; one
  read-back's is started once at most (`start`). It is handed the caller, the language of the
  action's lines and the wording its texts are read in (the read-back's: MSA for an MSA
  caller), the turn that said yes, and the call so far as the caller heard it (history.py's
  `lines`, for an action that attaches it: plan 007's Q7).
- **Its outcome** lands as a step of the session's (under its lock): the public `ActionCompleted`
  for `done`, `ActionUnconfirmed` for `failed` or `unknown`; and its line, the action's own
  template the runner rendered (`ActionOutcome.line`), is kept until the next turn boundary
  (`flush`): no reply in progress, every turn of the caller's closed and none awaiting its
  transcript, and no read-back waiting for its answer (read_back.py's `Confirming`), so it is
  never said over the caller, nor between another action's closing question and the caller's
  answer, where a yes to it would confirm that action; it follows the `sending` line. It is
  said once, as a reply of its own that answers no turn. A job that raises (a failed write is an
  outcome, never an exception, so only a bug does) is logged by its kind and told as the
  `error` notice; an outcome that lands once the call has ended or is ending is not said, and
  is logged by its action and kind alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from functools import partial
from typing import Any

from t2_agentic_voice.core.events import ActionCompleted, ActionUnconfirmed, ReplyId, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.yes_rule import ConfirmedAction
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talker_play import Guarded
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)
# The jobs still running, of every call: the event loop keeps only a weak reference to a task,
# so they are held here, and a job outlives the session that started it.
_RUNNING: set[asyncio.Task[None]] = set()


@dataclass(frozen=True, kw_only=True)
class _Due:
    """An outcome to say: its action, its line (None for a job that failed: the `error`
    notice), and the language the line is in."""

    action: str
    line: SpokenLine | None
    language: LanguageTag


class ActionJob:
    """One call's confirmed actions' writes (the module's docstring), each outcome said by
    `speaker` at a boundary of the turns `turns` keeps, the call's `confirming` state not
    waiting for an answer, landed as a step `guarded` runs, the client's state then brought up
    to date by `sync`; `over` says whether the call has ended or is ending."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        speaker: Speaker,
        turns: TurnBook,
        confirming: Confirming,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        over: Callable[[], bool],
    ) -> None:
        self._setup, self._speaker, self._turns = setup, speaker, turns
        self._confirming = confirming
        self._history, self._guarded, self._sync, self._over = books.history, guarded, sync, over
        self._started: set[ReplyId] = set()  # the read-backs whose confirmed action was started
        self._due: list[_Due] = []

    @property
    def wired(self) -> bool:
        """Whether the call has an `ActionJobs` to hand a confirmed action to."""
        return self._setup.action_jobs is not None

    def start(
        self,
        confirmed: ConfirmedAction,
        *,
        turn_id: TurnId,
        language: LanguageTag,
        wording: LanguageTag | None = None,
    ) -> bool:
        """Start `confirmed`'s write, the yes of the caller's turn `turn_id`, its lines said in
        `language` and read in `wording` (the read-back's), as a job of its own; whether it was
        (not with no `ActionJobs`, nor a second time for one read-back)."""
        setup, jobs = self._setup, self._setup.action_jobs
        if jobs is None or confirmed.reply_id in self._started:
            return False
        self._started.add(confirmed.reply_id)
        write = jobs.run(
            confirmed,
            caller=setup.caller,
            call_id=setup.call_id,
            language=language,
            wording=wording,
            turn_id=turn_id,
            conversation=self._history.lines(),
            clock=setup.clock,
        )
        name = f"action-{setup.call_id}-{confirmed.reply_id}"
        task = asyncio.create_task(self._run(confirmed.action, turn_id, language, write), name=name)
        _RUNNING.add(task)
        task.add_done_callback(_RUNNING.discard)
        _log.info("action_job_started", call_id=setup.call_id, action=confirmed.action)
        return True

    async def _run(
        self,
        action: str,
        turn_id: TurnId,
        language: LanguageTag,
        write: Coroutine[Any, Any, ActionOutcome],
    ) -> None:
        """The write, awaited outside every scope and lock, then its outcome landed as a step of
        the session's."""
        outcome: ActionOutcome | None = None
        try:
            outcome = await write
        except Exception as error:  # a failed write is an outcome: this is a bug
            failure, call_id = type(error).__qualname__, self._setup.call_id
            _log.error("action_job_failed", call_id=call_id, action=action, failure=failure)
        landed = partial(self._landed, action, turn_id, language, outcome)
        await self._guarded("action_outcome", landed)

    async def _landed(
        self, action: str, turn_id: TurnId, language: LanguageTag, outcome: ActionOutcome | None
    ) -> None:
        """The write's `outcome` (None for a job that failed), as a step of the session's: its
        event, then its line kept to say, unless the call has ended or is ending."""
        if outcome is not None:
            self._emit(action, turn_id, outcome)
        if self._over():
            kind = "failed" if outcome is None else outcome.kind
            _log.info(
                "action_outcome_unsaid", call_id=self._setup.call_id, action=action, kind=kind
            )
            return
        line = None if outcome is None else outcome.line
        self._due.append(_Due(action=action, line=line, language=language))
        await self._sync()

    def _emit(self, action: str, turn_id: TurnId, outcome: ActionOutcome) -> None:
        setup = self._setup
        call_id, at, request_id = setup.call_id, setup.clock.wall(), outcome.request_id
        if outcome.kind == "done":
            setup.emit(
                ActionCompleted(
                    call_id=call_id,
                    turn_id=turn_id,
                    at=at,
                    action=action,
                    request_id=request_id,
                    result=outcome.result_json,
                )
            )
            return
        unconfirmed = ActionUnconfirmed(
            call_id=call_id,
            turn_id=turn_id,
            at=at,
            action=action,
            request_id=request_id,
            kind=outcome.kind,
        )
        setup.emit(unconfirmed)

    async def flush(self, at: float) -> None:
        """Say each outcome due, once, at `at`, if it is a turn boundary (the module's
        docstring); nothing before one."""
        if not self._due or self._over() or not self._boundary():
            return
        due, self._due = self._due, []
        for each in due:
            if each.line is None:
                await self._speaker.notice("error", at)
            else:
                await self._speaker.say_line(each.line, language=each.language, at=at, turn_id=None)
            _log.info("action_outcome_said", call_id=self._setup.call_id, action=each.action)

    def end(self) -> None:
        """The call ended: an outcome still due is never said, logged by its action alone."""
        for each in self._due:
            _log.info("action_outcome_unsaid", call_id=self._setup.call_id, action=each.action)
        self._due.clear()

    def _boundary(self) -> bool:
        """Whether no reply is in progress, every turn of the caller's has closed, none of them
        with its transcript still awaited, and no read-back waits for its answer."""
        turns = self._turns
        if self._confirming.active or self._speaker.playback.in_progress():
            return False
        return turns.all_closed and not turns.awaited
