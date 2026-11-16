"""How each of the talker's replies runs, for voice/session/talking.py (each of its events
played by talker_play.py's `TalkPlayer`).

- **The run** (`TalkRunner`). The talker's reply to a turn is iterated in the reply's scope, each
  event kept while the reply is held or kept (talking.py's early start and kept reply), else
  played as one step of the session's (`guarded`, under its lock, in the order they came); what
  was kept is let out in order (`let_out`), each event guarded so a failure, logged by its kind
  alone, leaves the rest to play; and the reply is closed once its talker is done. The talker's
  stream is closed in the reply's scope, even when a cancel comes while an event of it waits
  (D-060), so the model's request never ends later, in the event loop's finalizer. A talker that
  fails is logged by its failure's kind alone, a provider's failure told (`ProviderFailed`), and
  the caller told (`tell`). Work let go (`cancel`) still counts the model requests it made while
  held or kept in the call's usage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from functools import partial

from t2_agentic_voice.agent.talker import ModelReplied, ModelRequested, Talker, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.talker_play import Talk, TalkPlayer

_log = get_logger(__name__)
# Play one of the talker's events in its reply, given at a time (talking.py's `_play`).
Play = Callable[["Talk", TalkerEvent, float], Awaitable[None]]


class TalkRunner:
    """Runs one call's talker replies (the module's run): `talker` writes each, each event is
    played by `play` as a step `guarded` runs, a failure is told by `player`, and the client
    is told what the agent is doing by `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        talker: Talker,
        player: TalkPlayer,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        play: Play,
    ) -> None:
        self._setup, self._clock, self._talker, self._player = setup, setup.clock, talker, player
        self._usage, self._events = books.usage, books.events
        self._guarded, self._sync, self._play = guarded, sync, play

    async def run(self, talk: Talk, turn: TalkerTurn) -> None:
        """Iterate the talker's reply to `turn` in `talk`'s scope, each event kept while held or
        kept, else played as a step of the session's; then the reply closed (the module's
        run)."""
        failure: Exception | None = None
        stream: AsyncIterator[TalkerEvent] | None = None
        try:
            stream = self._talker.reply(turn, scope=talk.scope)  # a team's may raise here
            async for event in stream:
                at = self._clock.now()
                if talk.held:
                    talk.pending.append((event, at))
                else:
                    await self._guarded("talker_event", partial(self._play, talk, event, at))
        except Exception as error:  # the talker's failure: told, and the reply closed
            failure = error
        finally:
            close = getattr(stream, "aclose", None)  # an async generator's, as a talker's is
            if close is not None:
                await close()
        if talk.held:
            talk.written, talk.failure = True, failure
            return
        await self._guarded("talker_end", partial(self._close, talk, failure))

    async def let_out(self, talk: Talk) -> None:
        """Play what `talk` kept, in order, each event guarded (`_held_event`), and close its
        reply when its talker is done."""
        while talk.pending:
            event, when = talk.pending.pop(0)
            await self._held_event(talk, event, when)
        if talk.written:
            await self._close(talk, talk.failure)

    async def cancel(self, talk: Talk) -> None:
        """`talk`'s work cancelled; the model requests it made while held or kept, which went
        though none of it will play, counted in the call's usage (usage.py) as they would have
        been."""
        await talk.scope.cancel()
        for event, _ in talk.pending:
            if isinstance(event, ModelRequested):
                self._usage.chat_requested(event.model)
            elif isinstance(event, ModelReplied):
                self._usage.chat_replied(event.model, event.usage)
        talk.pending.clear()

    async def _held_event(self, talk: Talk, event: TalkerEvent, at: float) -> None:
        """Play one event the hold kept, guarded as a step of the session's is (`run`'s): a
        failure logged by its kind alone, so the rest still plays and the reply closes."""
        try:
            await self._play(talk, event, at)
        except Exception as error:
            failure = type(error).__qualname__
            call_id = self._setup.call_id
            _log.error("session_step_failed", call_id=call_id, step="talker_event", failure=failure)

    async def _close(self, talk: Talk, failure: Exception | None) -> None:
        """Close `talk`'s reply, its talker done: a failure logged by its kind alone, a
        provider's told, and the caller told (`TalkPlayer.tell`), in its language, after its
        clauses too."""
        if talk.waiting is not None:
            talk.waiting.cancel()
        reply = talk.reply
        if reply is None:
            return
        now = self._clock.now()
        if failure is not None:
            kind = type(failure).__qualname__
            _log.warning("talker_failed", call_id=self._setup.call_id, failure=kind)
            if isinstance(failure, ProviderError):
                self._events.failed(failure.kind, failure.retryable, talk.turn_id)
            await self._player.tell(talk, reply, now)
        await reply.finish(now)
        await self._sync()
