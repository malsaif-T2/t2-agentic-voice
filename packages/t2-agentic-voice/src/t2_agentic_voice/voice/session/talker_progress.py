"""A tool's progress line with a time set (talking.py's **the progress line**; plan 006, Q27), for
voice/session/talking.py: a `ProgressDue` with an `after_s` waits, in the reply's scope, until
that long after the caller stopped speaking, and is said then only if no clause has been asked of
the voice by then, the reply is not kept and no notice took its place; past that time it is said
at once, and once a clause was asked for never, nor when its answer is already given behind it
(a clause or a read-back the early start's hold or a kept reply kept after it, now let out:
the answer then plays at once, not behind the line). Apart from talking.py so each stays within
the size a module may have (ARCH-SIZE).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

from t2_agentic_voice.agent.talker import (
    ProgressDue,
    ReadBackRequested,
    SpokenClause,
    TalkerEvent,
)
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.talker_play import Talk, TalkPlayer
from t2_agentic_voice.voice.session.turn_book import TurnBook


class ProgressLines:
    """One call's progress lines with a time set, timed from the turns `turns` keeps on the
    call's clock, each said late by `player` as a step `guarded` runs, the client's state then
    brought up to date by `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        turns: TurnBook,
        player: TalkPlayer,
        *,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
    ) -> None:
        self._clock, self._turns, self._player = setup.clock, turns, player
        self._guarded, self._sync = guarded, sync

    def now(self, talk: Talk, event: TalkerEvent) -> bool:
        """Whether `event` plays now: any but a progress line with a time set, which is said
        now only past its time with no answer begun or given behind it; before its time it
        waits (the module's docstring)."""
        if not isinstance(event, ProgressDue) or event.after_s <= 0:
            return True
        if talk.said or talk.told or _answer_behind(talk):
            return False
        now = self._clock.now()
        spoken = self._turns.turn(talk.turn_id).spoken_at
        left = (now if spoken is None else spoken) + event.after_s - now
        if left <= 0:
            return True
        talk.waiting = talk.scope.start(
            self._at(talk, event, left), name=f"progress-{talk.turn_id}"
        )
        return False

    async def _at(self, talk: Talk, event: ProgressDue, left: float) -> None:
        """Say `event`'s line in `left` seconds, as a step of the session's, if it is still
        wanted (the module's docstring)."""
        await self._clock.sleep(left)
        await self._guarded("talker_event", partial(self._said_late, talk, event))

    async def _said_late(self, talk: Talk, event: ProgressDue) -> None:
        if not (talk.said or talk.told or talk.held):
            await self._player.play(talk, event, self._clock.now())
            await self._sync()


def _answer_behind(talk: Talk) -> bool:
    """Whether `talk` already holds its answer behind the line: a clause or a read-back kept
    after it, still to be let out (the line is taken from `pending` before it plays)."""
    return any(isinstance(event, SpokenClause | ReadBackRequested) for event, _ in talk.pending)
