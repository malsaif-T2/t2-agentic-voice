"""When each of the caller's turns first heard its reply (`TurnAudio`, the base of turn_book.py's
`TurnBook`). Apart from turn_book.py so each stays within the size a module may have (ARCH-SIZE).

A turn's time to first audio (plan 006) ends at its reply's first audible frame sent: a piece of
the agent's audio the output tapped (`AgentAudio`) while a clause of the reply played, with a
sample louder than audible.py's `AUDIBLE_FLOOR`, so a silent first chunk is not audible
(TD-090); a progress line's is kept apart. A call whose output taps no audio (a test's,
`TextCall`'s) times the reply's first audio queued instead. The browser's `playback` report of
the reply's first clause other than a progress line ends the time to its playback there.
"""

from __future__ import annotations

from collections.abc import Callable

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.voice.protocol import ClauseIndex
from t2_agentic_voice.voice.session.audible import audible
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import AgentAudio


class TurnAudio:
    """When each turn's reply was first queued, heard and played (the module's docstring): the
    base of turn_book.py's `TurnBook`, which gives each turn's log by its number (`turn`)."""

    turn: Callable[[TurnId], TurnLog]

    def first_audio(self, reply: Reply, index: ClauseIndex, at: float) -> None:
        """Clause `index` of `reply` began playing at `at`: its turn's first audio, the first
        time, a progress line's apart."""
        if reply.turn_id is None or index >= len(reply.clauses):
            return
        turn = self.turn(reply.turn_id)
        if reply.clauses[index].progress:
            turn.progress_at = turn.progress_at or at
        else:
            turn.first_audio_at = turn.first_audio_at or at

    def heard_audio(self, playing: tuple[Reply, ClauseIndex] | None, event: AgentAudio) -> None:
        """The output sent `event`'s audio while `playing` played: the reply's turn's first
        audible frame, the first time, a progress line's apart."""
        reply, index = (None, 0) if playing is None else playing
        if reply is None or reply.turn_id is None:
            return
        turn = self.turn(reply.turn_id)
        turn.audio_seen = True
        progress = reply.clauses[index].progress
        if (turn.progress_audible_at if progress else turn.first_audible_at) is not None:
            return
        if audible(event.pcm16):
            if progress:
                turn.progress_audible_at = event.at
            else:
                turn.first_audible_at = event.at

    def browser_played(self, reply: Reply | None, index: ClauseIndex, at: float) -> None:
        """The browser began playing clause `index` of `reply` at `at` (its `playback`
        report): the reply's turn's playback, the first time, a progress line not counted."""
        if reply is None or reply.turn_id is None or index >= len(reply.clauses):
            return
        if not reply.clauses[index].progress:
            turn = self.turn(reply.turn_id)
            turn.played_at = turn.played_at or at
