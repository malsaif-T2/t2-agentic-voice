"""The kept reply (plan 006, Q19) of one call's talker replies (`KeptReplies`, the base of
talking.py's `Talking`). Apart from talking.py so each stays within the size a module may have
(ARCH-SIZE).

While a newer turn of the caller's is open, from its `TurnOpened` until it is taken (`taken`: its
own transcript answered, a command, or heard as nothing), and is no overlap of a reply of the
talker's (its speech began before any of that reply played, or before the reply was opened),
nothing more of that reply plays: what its talker gives is kept, in order, as the early start
keeps it (a clause asked for before plays on), its Smart Turn hold included. Heard with words,
the turn stops it, as talking.py's `answer` stops a reply in progress to an earlier turn (or its
early start's `release`); a stop or pause request said whole stops it (interrupter.py); heard as
nothing (an empty transcript, or the filter's text from silence) or failed, the turn lets it go
on: what was kept plays in order, each event guarded, and the rest as it comes. Once its reply
was stopped, or the call has ended or is ending, nothing kept plays. While kept, the reply has no
audio, so the client is shown `thinking`.
"""

from __future__ import annotations

from collections.abc import Callable

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talk_runner import TalkRunner
from t2_agentic_voice.voice.session.talker_play import Talk


class KeptReplies:
    """The replies kept behind the caller's newer turns (the module's docstring): the base of
    talking.py's `Talking`, which keeps each reply's talk (`_talks`), the turns open, no overlap,
    not yet taken (`_open`), the `_speaker`, the `_runner` and whether the call is `_over`."""

    _talks: dict[TurnId, Talk]
    _open: set[TurnId]
    _speaker: Speaker
    _runner: TalkRunner
    _over: Callable[[], bool]

    def opened(self, turn: TurnLog) -> None:
        """The caller's turn opened, no overlap and not dropped: each reply of the talker's in
        progress to an earlier turn, none of it played before the turn's speech began, is kept
        behind it until it is taken (the module's kept reply)."""
        if turn.overlap or turn.dropped:
            return
        self._open.add(turn.turn_id)
        began, playback = turn.speech_at or 0.0, self._speaker.playback
        for talk in self._talks.values():
            reply = None if talk.reply is None else playback.reply(talk.reply.reply_id)
            if reply is None or reply.ended_at is not None or talk.turn_id >= turn.turn_id:
                continue
            if reply.started_at is None or reply.started_at > began:
                talk.kept_for.add(turn.turn_id)

    async def taken(self, turn: TurnLog) -> None:
        """`turn` was taken, its own transcript answered, a command or heard as nothing: each
        reply kept behind it, and no other turn, plays what it kept, in order, and the rest as it
        comes; nothing once that reply was stopped or the call has ended or is ending, its work
        then cancelled (the module's kept reply)."""
        self._open.discard(turn.turn_id)
        for talk in list(self._talks.values()):
            if turn.turn_id not in talk.kept_for:
                continue
            talk.kept_for.discard(turn.turn_id)
            if talk.kept_for or talk.reply is None:
                continue
            reply = self._speaker.playback.reply(talk.reply.reply_id)
            if self._over() or reply is None or reply.ended_at is not None:
                await self._runner.cancel(talk)
            else:
                await self._runner.let_out(talk)

    def _newer(self, turn_id: TurnId) -> set[TurnId]:
        """The turns open, no overlap and not yet taken, newer than `turn_id`: a reply to it
        opened now is kept behind them (the module's kept reply)."""
        return {each for each in self._open if each > turn_id}
