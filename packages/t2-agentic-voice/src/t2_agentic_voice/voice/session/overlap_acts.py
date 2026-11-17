"""How one call's session carries out an overlap's verdict (`OverlapActs`, the base of
interrupter.py's `Interrupter`), apart from interrupter.py so each stays within the size a module
may have (ARCH-SIZE).

- **stop:** every reply asked for is dropped (`StopSpeaking`), which cancels each one's scope,
  `unduck` right after it, the clause playing marked cut (its caption sent again with the mark)
  and in the heard history; one `Interrupted` of the verdict's kind and reason. A stop or pause
  word's turn is taken as a command and never said back; new words or a correction are
  answered (the echo) from the turn's own transcript, and so are those of the whole overlap,
  judged still after a window's stop (it may hold only a request's first word).
- **repeat:** stopped as above, then the last reply the caller heard is said again, as the reply
  answering the turn, a command, once the whole overlap's transcript has come, so it never
  starts while the caller still speaks; new words (or a correction) in it are answered instead.
- **go_on:** `unduck`, the turn not answered (it `went_on`), and an `Interrupted` of kind
  `false`. When speech followed in the same turn, its own transcript is judged again once it
  comes (no request: `_judged_again`), and may still stop the agent.
- **A whole command** said as a reply began stops the replies in progress to earlier turns first
  (`_stop_earlier`), with one `Interrupted` as an overlap's stop or repeat would give.
- **A read-back said again** (`_read_again`) is read_back_moved.py's `read_again`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.interruptions import REPEAT_WORD, STOP_WORD, Verdict, WholeCommand
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState, answers
from t2_agentic_voice.voice.session.overlap_follow import Follows
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.read_back_moved import read_again
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import CallEvents, TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook

# What a whole command said as a reply began stops it as: an overlap's stop word or repeat.
_STOPS: Mapping[WholeCommand, Verdict] = {"stop": STOP_WORD, "repeat": REPEAT_WORD}


class OverlapActs:
    """What carries out an overlap's verdict (the module's docstring): the base of
    interrupter.py's `Interrupter`, which sets each part below."""

    _speaker: Speaker
    _turns: TurnBook
    _overlaps: Overlaps
    _follows: Follows
    _confirming: Confirming
    _events: CallEvents
    _recorder: CallRecorder
    _over: Callable[[], bool]
    _talker: bool
    _own_s: float

    async def _judged_again(
        self, state: OverlapState | None, turn: TurnLog, event: Transcribed
    ) -> Verdict | None:
        """The verdict that decided the overlap `state` (None for no overlap, or one undecided):
        after a verdict to go on, the turn's own transcript `event` judged again when speech
        followed it (`Overlaps.judge_after`), and a verdict that stops the agent carried out
        then, deciding it in the go-on's place."""
        decided = None if state is None else state.decided
        if state is None or decided is None or decided.action != "go_on":
            return decided
        played = self._played(state)
        again = self._overlaps.judge_after(event, played=played, ended_at=turn.speech_ended_at)
        if again is None or again.action == "go_on":
            return decided
        self._judged(event, again)
        await self._act(state, again, event.at)
        return again

    async def _stop_earlier(self, turn: TurnLog, command: WholeCommand, at: float) -> None:
        """Before `turn`'s whole `command`: the replies in progress to earlier turns stopped,
        with one `Interrupted` as an overlap's, of the newest of their turns (playback.py's
        `Playback.earlier`)."""
        earlier = self._speaker.playback.earlier(turn.turn_id)
        if not earlier:
            return
        await self._speaker.stop(at, client=False)
        verdict = _STOPS[command]
        newest = max(reply.turn_id or 0 for reply in earlier)
        self._events.interrupted(newest, verdict.kind, verdict.reason)

    async def _act(self, state: OverlapState, verdict: Verdict, at: float) -> None:
        """Carry out `verdict` on the overlap `state`: its `Interrupted`, the turn's fate, and
        for a stop or a repeat, the stop and what follows it; each `unduck` now due."""
        turn = self._turns.turn(state.turn_id)
        unducks = self._overlaps.settle()
        if verdict.action == "go_on":
            self._turns.ended(turn, "went_on")
            for _ in range(unducks):
                await self._speaker.send(Unduck())
        else:
            over = self._speaker.playback.reply(state.reply_id)
            if over is not None and over.ended_at is None:  # not one heard whole, in its tail
                turn.cut_reply = state.reply_id
            self._confirming.cut_by(
                turn.turn_id, reply_id=state.reply_id, speech_at=state.speech_at, verdict=verdict
            )
            await self._speaker.stop(at, client=False, unducks=unducks)
            if self._talker:
                self._turns.ended(turn, "pending")  # the talker reads it whole
            elif verdict.action == "repeat" and state.decided_by == "window":
                # said again once the whole overlap is heard
                self._follows.repeats.add(turn.turn_id)
            else:
                if verdict.action == "repeat":
                    await self._follows.repeat(turn, at)
                self._turns.ended(turn, "pending" if answers(verdict) else "command")
        spoken = self._speaker.playback.reply(state.reply_id)
        turn_id = None if spoken is None else spoken.turn_id
        self._events.interrupted(turn_id, verdict.kind, verdict.reason)

    async def _read_again(self, turn: TurnLog, plan: ReadBackPlan, at: float) -> None:
        """Say `plan`'s read-back again, as the reply answering `turn` (read_back.py's
        `read_again`), unless the call has ended or is ending."""
        if not self._over():
            reply_id = await read_again(
                self._speaker, self._confirming, plan, turn_id=turn.turn_id, at=at
            )
            turn.reply_id = reply_id

    def _played(self, state: OverlapState) -> tuple[str, ...]:
        """What the agent's own voice heard back would say over the overlap: the clauses that
        played within `own_words_s` before its speech began, or since, and the one playing."""
        return self._speaker.playback.heard_since(state.speech_at - self._own_s)

    def _judged(self, event: Transcribed, verdict: Verdict) -> None:
        self._recorder.judged(event, verdict)
