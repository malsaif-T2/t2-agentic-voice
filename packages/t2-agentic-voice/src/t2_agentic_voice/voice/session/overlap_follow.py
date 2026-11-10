"""What follows an overlap's stop word or repeat request (interrupter.py's **repeat** and **what
followed**; plan 005), for voice/session/interrupter.py, which keeps a `Follows` and asks it: the
last reply said again (`repeat`); a window's repeat request followed once its whole overlap's
verdict came (`follow`), unless the whole overlap holds new words or a correction; and the turn's
own transcript read for what followed the request that decided its overlap (`read_on`). Apart
from interrupter.py so each stays within the size a module may have (ARCH-SIZE).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.domain.interruptions import WholeCommand, after_command, whole_command
from t2_agentic_voice.domain.words import Words, rule_form
from t2_agentic_voice.voice.session.heard import with_text
from t2_agentic_voice.voice.session.overlap import OverlapState
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook

# Answer the caller's turn (interrupter.py's `Answer`).
Answer = Callable[[TurnLog, HeardWords | None, Transcribed], Awaitable[None]]


class Follows:
    """What follows one call's overlaps' stop words and repeat requests, said by `speaker` for
    the turns `turns` keeps, read with the call's `words`; `over` says whether the call has ended
    or is ending, and `answer` answers a turn."""

    def __init__(
        self,
        *,
        speaker: Speaker,
        turns: TurnBook,
        over: Callable[[], bool],
        answer: Answer,
        words: Words,
        min_words: int,
    ) -> None:
        self._speaker, self._turns, self._over, self._answer = speaker, turns, over, answer
        self._words, self._min_words = words, min_words
        self.repeats: set[TurnId] = set()  # each window's repeat request still to follow

    def pending(self, turn: TurnLog) -> TurnLog:
        """`turn`, to be answered now: `pending` again, after a stop that made it a command."""
        if turn.fate != "pending":
            self._turns.ended(turn, "pending")
        return turn

    async def read_on(
        self, state: OverlapState, turn: TurnLog, heard: HeardWords | None, event: Transcribed
    ) -> None:
        """What followed, in the turn, the stop word or the repeat request that decided its
        overlap (interrupter.py's what followed); a repeat its window's request still waits for
        is said now, unless new words followed it, answered instead."""
        words = self._words
        stopped = state.decided is not None and state.decided.action == "stop"
        command: WholeCommand = "stop" if stopped else "repeat"
        rest = "" if heard is None else after_command(heard.text, command, words=words)
        found = whole_command(rest, words=words)
        enough = len(rule_form(rest).split()) >= (1 if stopped else self._min_words)
        if heard is not None and found is None and enough:
            self.repeats.discard(turn.turn_id)
            turn.reply_id = None  # a reply said again plays on before the answer
            await self._answer(self.pending(turn), with_text(heard, rest), event)
            return
        if turn.turn_id in self.repeats:
            await self.follow(state, event.at)
        elif stopped and found == "repeat":
            await self.repeat(turn, event.at)
            self._turns.ended(turn, "command")
        self._turns.settle(turn)

    async def follow(self, state: OverlapState, at: float) -> None:
        """What follows the stop its window's repeat request gave, once its whole overlap's
        verdict came, or its turn's own transcript when none will: the last reply said again, a
        command; unless the whole overlap holds new words or a correction, which are answered
        instead, from the turn's own transcript (`OverlapState.instead`)."""
        self.repeats.discard(state.turn_id)
        if not state.instead:
            turn = self._turns.turn(state.turn_id)
            await self.repeat(turn, at)
            self._turns.ended(turn, "command")

    async def repeat(self, turn: TurnLog, at: float) -> None:
        """Say the last reply the caller heard again, as the reply answering `turn`, unless
        the call has ended or is ending."""
        if not self._over():
            reply = await self._speaker.repeat(at, turn_id=turn.turn_id)
            turn.reply_id = None if reply is None else reply.reply_id
