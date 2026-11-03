"""How one call's session takes the caller's speech over a reply under `interruptions.mode =
"two_step"` (io.py's overlaps; plan 005), for voice/session/call.py: the `Interrupter` opens each
overlap (`duck`, then `HearOverlap`), judges its transcripts as they come (overlap.py's
`Overlaps`), and carries out each verdict.

- **stop:** every reply asked for is dropped (`StopSpeaking`), which cancels each one's scope,
  `unduck` right after it, the clause playing marked cut (its caption sent again with the mark)
  and in the heard history; one `Interrupted` of the verdict's kind and reason. A stop or pause
  word's turn is taken as a command and never said back; new words or a correction are
  answered (the echo) from the turn's own transcript.
- **repeat:** stopped as above, then the last reply the caller heard is said again, as the reply
  answering the turn, a command.
- **go_on:** `unduck`, the turn not answered (it `went_on`), and an `Interrupted` of kind
  `false`. When speech followed in the same turn, its own transcript is judged again once it
  comes (no request), and may still stop the agent.

Each `unduck` waits until no overlap of the call is undecided (`Overlaps.settle`). The turn's own
transcript that comes while its overlap's whole transcript is still awaited is held, and taken
once the overlap is decided. Every verdict judged is a line of the call's timeline, when it is
recorded.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.heard import HeardWords
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing, TurnOpened
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook

# Answer the caller's turn: the session's echo of its own transcript (call.py).
Answer = Callable[[TurnLog, HeardWords | None, Transcribed], Awaitable[None]]


def answers(verdict: Verdict) -> bool:
    """Whether the turn behind `verdict` is answered: new words or a correction that stopped
    the agent; a stop or pause word, a repeat request or a verdict to go on is not."""
    return verdict.action == "stop" and verdict.kind in ("new_words", "correction")


class Interrupter:
    """One call's overlaps as the session carries them out; `over` says whether the call has
    ended or is ending, and `answer` answers a turn."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        books: CallBooks,
        *,
        speaker: Speaker,
        turns: TurnBook,
        over: Callable[[], bool],
        answer: Answer,
    ) -> None:
        self._commands, self._speaker, self._turns = commands, speaker, turns
        self._usage, self._recorder, self._events = books.usage, books.recorder, books.events
        self._over, self._answer = over, answer
        self._own_s = setup.settings.interruptions.own_words_s
        self._overlaps = Overlaps(setup)
        self._held: dict[TurnId, tuple[TurnLog, HeardWords | None, Transcribed]] = {}

    async def opened(self, event: TurnOpened, over: Reply) -> None:
        """The turn `event` opens is an overlap of `over`: the agent's voice lowered, and the
        overlap's transcripts asked for."""
        turn_id, at = event.turn_id, event.at
        commands = self._overlaps.open(
            turn_id, reply_id=over.reply_id, speech_at=event.speech_at, at=at
        )
        self._recorder.line(at, "overlap", turn_id=turn_id, reply_id=over.reply_id)
        for command in commands:
            await self._commands.run(command)

    def requested(self, event: Transcribing) -> None:
        """A request of a turn went: an overlap's turn keeps which."""
        self._overlaps.requested(event)

    async def heard(self, event: Transcribed) -> None:
        """An overlap's window or whole transcript came, in whichever order: its request's
        failure told, then judged, and the verdict carried out once it decides; a turn's own
        transcript held for it is then taken. One that comes once the overlap is decided (a
        window after the whole overlap, or a part after the turn's own transcript decided it)
        changes nothing. A part with no request of its own (it reuses the turn's) is timed to
        when the turn's speech ended."""
        self._usage.transcribed(event)
        state = self._overlaps.get(event.turn_id)
        if state is None:
            return
        asked = event.part in state.asked
        if event.failure is not None and asked:
            self._events.failed(event.failure, event.retryable, event.turn_id)
        ended = None if asked else self._turns.turn(event.turn_id).speech_ended_at
        verdict = self._overlaps.judge(event, played=self._played(state), ended_at=ended)
        if verdict is None:
            return
        self._judged(event, verdict)
        if state.decided is None:
            return
        await self._act(state, verdict, event.at)
        held = self._held.pop(event.turn_id, None)
        if held is not None:
            await self._take(*held)

    async def turn_heard(self, turn: TurnLog, heard: HeardWords | None, event: Transcribed) -> None:
        """The overlap's turn's own transcript came: held while its whole overlap's is still
        awaited; otherwise taken, deciding the overlap when nothing else will."""
        state = self._overlaps.get(turn.turn_id)
        if state is not None and state.decided is None:
            if state.waiting:
                self._held[turn.turn_id] = (turn, heard, event)
                return
            ended = turn.speech_ended_at
            verdict = self._overlaps.judge(event, played=self._played(state), ended_at=ended)
            if verdict is not None:
                self._judged(event, verdict)
                await self._act(state, verdict, event.at)
        await self._take(turn, heard, event)

    async def _take(self, turn: TurnLog, heard: HeardWords | None, event: Transcribed) -> None:
        """The turn's own transcript, its overlap decided: answered when the verdict says so;
        after a verdict to go on, judged again when speech followed it."""
        state = self._overlaps.get(turn.turn_id)
        decided = None if state is None else state.decided
        if state is not None and decided is not None and decided.action == "go_on":
            played = self._played(state)
            again = self._overlaps.judge_after(event, played=played, ended_at=turn.speech_ended_at)
            if again is not None and again.action != "go_on":
                self._judged(event, again)
                await self._act(state, again, event.at)
                decided = again
        if decided is None or answers(decided):
            await self._answer(turn, heard, event)
        else:
            self._turns.settle(turn)

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
            await self._speaker.stop(at, client=False, unducks=unducks)
            if verdict.action == "repeat" and not self._over():
                reply = await self._speaker.repeat(at, turn_id=turn.turn_id)
                turn.reply_id = None if reply is None else reply.reply_id
            self._turns.ended(turn, "pending" if answers(verdict) else "command")
        spoken = self._speaker.playback.reply(state.reply_id)
        turn_id = None if spoken is None else spoken.turn_id
        self._events.interrupted(turn_id, verdict.kind, verdict.reason)

    def _played(self, state: OverlapState) -> tuple[str, ...]:
        """What the agent's own voice heard back would say over the overlap: the clauses that
        played within `own_words_s` before its speech began, or since, and the one playing."""
        return self._speaker.playback.heard_since(state.speech_at - self._own_s)

    def _judged(self, event: Transcribed, verdict: Verdict) -> None:
        text = "" if event.transcript is None else event.transcript.text
        self._recorder.line(
            event.at,
            "overlap_judged",
            turn_id=event.turn_id,
            part=event.part,
            text=text,
            action=verdict.action,
            kind=verdict.kind,
            reason=verdict.reason,
        )
