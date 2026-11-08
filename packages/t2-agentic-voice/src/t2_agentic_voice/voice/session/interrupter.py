"""How one call's session takes the caller's speech over a reply under `interruptions.mode =
"two_step"` (io.py's overlaps; plan 005), for voice/session/call.py: the `Interrupter` opens each
overlap (`duck`, then `HearOverlap`), judges its transcripts as they come (overlap.py's
`Overlaps`), and carries out each verdict; and it reads each other turn, said while the agent was
silent, for a command said whole (`alone`).

- **stop:** every reply asked for is dropped (`StopSpeaking`), which cancels each one's scope,
  `unduck` right after it, the clause playing marked cut (its caption sent again with the mark)
  and in the heard history; one `Interrupted` of the verdict's kind and reason. A stop or pause
  word's turn is taken as a command and never said back; new words or a correction are
  answered (the echo) from the turn's own transcript, and so are those of the whole overlap,
  judged still after a window's stop (it may hold only a request's first word).
- **repeat:** stopped as above, then the last reply the caller heard is said again, as the reply
  answering the turn, a command; but once the whole overlap's transcript has come, so it never
  starts while the caller still speaks: after a window's repeat request, the whole overlap is
  judged still, and new words (or a correction) in it are answered instead.
- **go_on:** `unduck`, the turn not answered (it `went_on`), and an `Interrupted` of kind
  `false`. When speech followed in the same turn, its own transcript is judged again once it
  comes (no request), and may still stop the agent.
- **what followed:** when speech followed, in the same turn, the transcript whose stop word or
  repeat request decided the overlap, the turn's own transcript is read with that request taken
  off (domain/interruptions.py's `after_command`), at no request: after a stop word, a whole
  repeat request says the last reply again, a stop or nothing leaves a command, and anything
  else is answered, the echo saying back what followed; after a repeat request, new words (no
  whole command, at least `min_words` words) are answered so, and the repeat stands otherwise.

A verdict to go on for want of words on two or more words, in a call whose agent asks for it,
leaves the overlap undecided for a chat model's word (overlap_ask.py, D-069), the reply playing on
ducked, its `stop` carried out as new words (`model_said`); everything above then follows.

Each `unduck` waits until no overlap of the call is undecided (`Overlaps.settle`). The turn's own
transcript that comes while its overlap's whole transcript is still awaited, or the model's word,
is held, and taken once the overlap is decided (and its window's repeat request followed). Every
verdict judged is a line of the call's timeline, when it is recorded.

A turn said while the agent was silent (no overlap) is read whole under `two_step`
(domain/interruptions.py's `whole_command`): a repeat request says the last reply again, and a
stop or pause request is never said back, each a command, once the replies in progress to
earlier turns are stopped (its speech began before they started, so no overlap of them), with
one `Interrupted`; any other is answered. Under `drop` every such turn is answered, as plan
003's echo answers it.

**With a talker** (plan 006, "What voice-first means here", item 2) the talker reads what the
caller meant, so the rule keeps only what cannot wait for a model: the agent's voice lowered at
once; a stop at once on a stop or pause word, a repeat request or real words over a reply (the
verdicts above, `StopSpeaking` before any model request); and the reply going on for a listening
sound, the agent's own echo or silence. Once a stop or a repeat request stopped the agent, the
turn's own transcript reaches the talker whole, its stop word included (TD-103), with the reply
it cut (`TurnLog.cut_reply`; none when the reply had ended and the speech began in its tail),
unless it is a stop or pause request said whole, which is a command and answered by nothing;
new words or a correction whose own transcript failed hear the `error` notice, as with no
talker, and so do those the whole overlap held after a window's stop or repeat request; what
followed is not read apart, and the reply is never said again by the session. A repeat request
said while the agent was silent is answered by the talker too; a stop or pause request said
whole stays a command. The fixed repeat (D-064) stays only for a session with no talker.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.interruptions import (
    Verdict,
    WholeCommand,
    after_command,
    whole_command,
)
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.heard import HeardWords
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState, answers
from t2_agentic_voice.voice.session.overlap_ask import OverlapAsks
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing, TurnOpened
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talking import Guarded
from t2_agentic_voice.voice.session.turn_book import TurnBook

# Answer the caller's turn: the session's echo of its own transcript (call.py).
Answer = Callable[[TurnLog, HeardWords | None, Transcribed], Awaitable[None]]
# What a whole command said as a reply began stops it as: an overlap's stop word or repeat.
_STOPS: Mapping[WholeCommand, Verdict] = {
    "stop": Verdict(action="stop", kind="stop", reason="stop_word"),
    "repeat": Verdict(action="repeat", kind="new_words", reason="repeat_word"),
}


class Interrupter:
    """One call's overlaps as the session carries them out; `over` says whether the call has
    ended or is ending, `answer` answers a turn, and `guarded` and `sync` run a chat model's
    word on an uncertain overlap as a step of the session's (overlap_ask.py)."""

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
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
    ) -> None:
        self._commands, self._speaker, self._turns = commands, speaker, turns
        self._sync = sync
        self._usage, self._recorder, self._events = books.usage, books.recorder, books.events
        self._over, self._answer = over, answer
        self._two_step = setup.settings.interruptions.mode == "two_step"
        self._own_s = setup.settings.interruptions.own_words_s
        self._min_words = setup.settings.interruptions.min_words
        self._overlaps = Overlaps(setup)
        self._talker = setup.talker is not None
        self.asks = OverlapAsks(setup, books, guarded=guarded, over=over, decide=self.model_said)
        self._held: dict[TurnId, tuple[TurnLog, HeardWords | None, Transcribed]] = {}
        self._repeats: set[TurnId] = set()  # each window's repeat request still to follow

    async def opened(self, event: TurnOpened, over: Reply) -> None:
        """The turn `event` opens is an overlap of `over`: the agent's voice lowered, and the
        overlap's transcripts asked for."""
        turn_id, at = event.turn_id, event.at
        self._turns.turn(turn_id).over_reply = over.reply_id
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
            self._ask(state)
            return
        if event.turn_id in self._repeats:
            await self._follow(state, event.at)
        elif state.decided_by == event.part:
            await self._act(state, verdict, event.at)
        held = self._held.pop(event.turn_id, None)
        if held is not None:
            await self._take(*held)

    async def turn_heard(self, turn: TurnLog, heard: HeardWords | None, event: Transcribed) -> None:
        """The overlap's turn's own transcript came: held while its whole overlap's is still
        awaited (to decide it, or to say what follows its window's stop or repeat request);
        otherwise taken, deciding the overlap when nothing else will."""
        state = self._overlaps.get(turn.turn_id)
        if state is not None and state.awaits:
            self._held[turn.turn_id] = (turn, heard, event)
            return
        if state is not None and state.decided is None:
            ended = turn.speech_ended_at
            verdict = self._overlaps.judge(event, played=self._played(state), ended_at=ended)
            if verdict is not None:
                self._judged(event, verdict)
                if state.asking is not None:  # a model is asked: the turn waits for its word
                    self._held[turn.turn_id] = (turn, heard, event)
                    self._ask(state)
                    return
                await self._act(state, verdict, event.at)
        await self._take(turn, heard, event)

    async def alone(self, turn: TurnLog, heard: HeardWords | None, event: Transcribed) -> None:
        """A turn's own transcript that is no overlap's: under `two_step`, a whole repeat
        request says the last reply again, and a whole stop or pause request is not said back,
        each a command, the replies answering earlier turns stopped first (`_stop_earlier`);
        any other is answered, as under `drop`."""
        command = None if self._over() else self.command(heard)
        if command is None or (command == "repeat" and self._talker):
            await self._answer(turn, heard, event)
            return
        self._recorder.line(event.at, "command", turn_id=turn.turn_id, command=command)
        await self._stop_earlier(turn, command, event.at)
        if command == "repeat":
            await self._repeat(turn, event.at)
        self._turns.ended(turn, "command")
        self._turns.settle(turn)

    def _ask(self, state: OverlapState) -> None:
        """The overlap's transcript waits for a chat model's word: its request starts, off the
        session's lock (overlap_ask.py), the reply playing on ducked."""
        if state.asking is not None:
            spoken = self._speaker.playback.reply(state.reply_id)
            self.asks.start(state, "" if spoken is None else spoken.text)

    async def model_said(
        self, state: OverlapState, verdict: Verdict, event: Transcribed, at: float
    ) -> None:
        """The model's word (or the rule's when it gave none) decided the overlap: carried out
        as a step of the session's, a turn's own transcript held for it then taken."""
        self._judged(replace(event, at=at), verdict)
        await self._act(state, verdict, at)
        held = self._held.pop(state.turn_id, None)
        if held is not None:
            await self._take(*held)
        await self._sync()

    def command(self, heard: HeardWords | None) -> WholeCommand | None:
        """What `heard`, a turn said while the agent was silent, asks as a whole under
        `two_step` (domain/interruptions.py's `whole_command`); None under `drop`."""
        if not self._two_step or heard is None:
            return None
        return whole_command(heard.text, words=self._overlaps.words)

    async def _take(self, turn: TurnLog, heard: HeardWords | None, event: Transcribed) -> None:
        """The turn's own transcript, its overlap decided: answered when the verdict says so
        (its window's repeat request followed first, when no whole overlap came); after a
        verdict to go on, judged again when speech followed it; after a stop word or a repeat
        request that speech followed, what followed read (`_read_on`). With a talker, the
        talker's (`_hand_over`)."""
        state = self._overlaps.get(turn.turn_id)
        if self._talker:
            await self._hand_over(state, turn, heard, event)
            return
        if state is not None and state.reads_on:
            await self._read_on(state, turn, heard, event)
            return
        decided = None if state is None else state.decided
        if state is not None and decided is not None and decided.action == "go_on":
            played = self._played(state)
            again = self._overlaps.judge_after(event, played=played, ended_at=turn.speech_ended_at)
            if again is not None and again.action != "go_on":
                self._judged(event, again)
                await self._act(state, again, event.at)
                decided = again
        if state is not None and turn.turn_id in self._repeats:
            await self._follow(state, event.at)
        if decided is None or answers(decided) or (state is not None and state.instead):
            await self._answer(self._pending(turn), heard, event)
        else:
            self._turns.settle(turn)

    async def _read_on(
        self, state: OverlapState, turn: TurnLog, heard: HeardWords | None, event: Transcribed
    ) -> None:
        """What followed, in the turn, the stop word or the repeat request that decided its
        overlap (the module's what followed); a repeat its window's request still waits for is
        said now, unless new words followed it, answered instead."""
        words = self._overlaps.words
        stopped = state.decided is not None and state.decided.action == "stop"
        command: WholeCommand = "stop" if stopped else "repeat"
        rest = "" if heard is None else after_command(heard.text, command, words=words)
        found = whole_command(rest, words=words)
        enough = len(rule_form(rest).split()) >= (1 if stopped else self._min_words)
        if heard is not None and found is None and enough:
            self._repeats.discard(turn.turn_id)
            turn.reply_id = None  # a reply said again plays on before the answer
            await self._answer(self._pending(turn), replace(heard, text=rest), event)
            return
        if turn.turn_id in self._repeats:
            await self._follow(state, event.at)
        elif stopped and found == "repeat":
            await self._repeat(turn, event.at)
            self._turns.ended(turn, "command")
        self._turns.settle(turn)

    async def _hand_over(
        self,
        state: OverlapState | None,
        turn: TurnLog,
        heard: HeardWords | None,
        event: Transcribed,
    ) -> None:
        """The turn's own transcript, its overlap decided, in a call with a talker (the
        module's): after a verdict to go on, judged again when speech followed it; once the
        agent was stopped, the turn handed to the talker whole, unless it is a stop or pause
        request said whole, or nothing was heard (a command); new words or a correction whose
        own transcript failed hear the `error` notice, as with no talker, and so do those its
        whole overlap held after its window's stop or repeat request (`OverlapState.instead`)."""
        decided = None if state is None else state.decided
        if state is not None and decided is not None and decided.action == "go_on":
            played = self._played(state)
            again = self._overlaps.judge_after(event, played=played, ended_at=turn.speech_ended_at)
            if again is not None and again.action != "go_on":
                self._judged(event, again)
                await self._act(state, again, event.at)
                decided = again
        if decided is not None and decided.action == "go_on":
            self._turns.settle(turn)
            return
        answered = decided is None or answers(decided) or (state is not None and state.instead)
        failed = event.failure is not None and answered
        if state is not None and not failed and (heard is None or self.command(heard) == "stop"):
            self._turns.ended(turn, "command")
            self._turns.settle(turn)
            return
        await self._answer(self._pending(turn), heard, event)

    def _pending(self, turn: TurnLog) -> TurnLog:
        """`turn`, to be answered now: `pending` again, after a stop that made it a command."""
        if turn.fate != "pending":
            self._turns.ended(turn, "pending")
        return turn

    async def _stop_earlier(self, turn: TurnLog, command: WholeCommand, at: float) -> None:
        """Before `turn`'s whole `command`: the replies in progress to earlier turns stopped,
        with one `Interrupted` as an overlap's; none when one answers this turn or a later one,
        which the stop would drop too."""
        playback = self._speaker.playback
        answering = [r.turn_id for r in playback.in_progress() if r.turn_id is not None]
        if not answering or max(answering) >= turn.turn_id:
            return
        await self._speaker.stop(at, client=False)
        verdict = _STOPS[command]
        self._events.interrupted(max(answering), verdict.kind, verdict.reason)

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
            await self._speaker.stop(at, client=False, unducks=unducks)
            if self._talker:
                self._turns.ended(turn, "pending")  # the talker reads it whole
            elif verdict.action == "repeat" and state.decided_by == "window":
                self._repeats.add(turn.turn_id)  # said again once the whole overlap is heard
            else:
                if verdict.action == "repeat":
                    await self._repeat(turn, at)
                self._turns.ended(turn, "pending" if answers(verdict) else "command")
        spoken = self._speaker.playback.reply(state.reply_id)
        turn_id = None if spoken is None else spoken.turn_id
        self._events.interrupted(turn_id, verdict.kind, verdict.reason)

    async def _follow(self, state: OverlapState, at: float) -> None:
        """What follows the stop its window's repeat request gave, once its whole overlap's
        verdict came, or its turn's own transcript when none will: the last reply said again, a
        command; unless the whole overlap holds new words or a correction, which are answered
        instead, from the turn's own transcript (`OverlapState.instead`)."""
        self._repeats.discard(state.turn_id)
        if not state.instead:
            turn = self._turns.turn(state.turn_id)
            await self._repeat(turn, at)
            self._turns.ended(turn, "command")

    async def _repeat(self, turn: TurnLog, at: float) -> None:
        """Say the last reply the caller heard again, as the reply answering `turn`, unless
        the call has ended or is ending."""
        if not self._over():
            reply = await self._speaker.repeat(at, turn_id=turn.turn_id)
            turn.reply_id = None if reply is None else reply.reply_id

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
