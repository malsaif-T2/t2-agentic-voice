"""How one call's session takes the caller's speech over a reply under `interruptions.mode =
"two_step"` (io.py's overlaps), for voice/session/call.py: the `Interrupter` opens each overlap
(`duck`, then `HearOverlap`), judges its transcripts as they come (overlap.py's `Overlaps`, whose
docstring says when each decides and when each `unduck` goes), and carries out each verdict; and
it reads each other turn, said while the agent was silent, for a command said whole (`alone`).

- **stop, repeat, go_on:** what each verdict does is overlap_acts.py's (`OverlapActs`, this
  class's base).
- **what followed** a stop word or a repeat request in the same turn is read from the turn's own
  transcript and carried out by overlap_follow.py's `Follows`, with the repeat.

A verdict to go on for want of words, in a call whose agent asks, waits for a chat model's word
(overlap_ask.py, D-069), carried out as a step of the session's (`model_said`). The turn's own
transcript that comes while its overlap is undecided, or its window's repeat request is to be
followed, is held and taken once it is (`_take`). Every verdict judged is a line of the call's
timeline, when it is recorded.

A turn said while the agent was silent (no overlap) is read whole under `two_step`
(domain/interruptions.py's `whole_command`): a repeat request says the last reply again, and a
stop or pause request is never said back, each a command, once the replies in progress to
earlier turns are stopped (playback.py's `Playback.earlier`), with one `Interrupted`; any other
is answered. Under `drop` every such turn is answered.

**With a talker** the talker reads what the caller meant, so the rule keeps only what cannot wait
for a model: the agent's voice lowered at once, a stop at once (`StopSpeaking` before any model
request), and the reply going on for a listening sound, the agent's own echo or silence. Once a
stop or a repeat request stopped the agent, the turn's own transcript reaches the talker whole,
its stop word included (TD-103), with the reply it cut (`TurnLog.cut_reply`; none when the reply
had ended and the speech began in its tail), unless it is a stop or pause request said whole, a
command answered by nothing; new words or a correction whose own transcript failed hear the
`error` notice, as with no talker, and so do those the whole overlap held after a window's stop
or repeat request; what followed is not read apart, and the session never says the reply again
(`_hand_over`). A repeat request said while the agent was silent is the talker's too; a stop or
pause request said whole stays a command. The fixed repeat (D-064) is a session's with no talker.

**Over an action's read-back** a stop that cuts it is told to the call's confirming state first
(`Confirming.cut_by`), and a repeat request over it, or said whole while it is confirming, has
the session say it again (`_read_again`): read_back.py says what each does to it.

**A yes over a reply's closing question** that it went on over, under
`interruptions.answer_yes_over_question` (D-116), is held until the reply ends, then answered as
the caller's next turn unless words said after it let it go (yes_over_question.py; `flush`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.interruptions import Verdict, WholeCommand, whole_command
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Commands, Guarded
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState, answers
from t2_agentic_voice.voice.session.overlap_acts import OverlapActs
from t2_agentic_voice.voice.session.overlap_ask import OverlapAsks
from t2_agentic_voice.voice.session.overlap_follow import Answer, Follows
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.read_back_heard import takes
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing, TurnOpened
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.yes_over_question import YesOverQuestion


class Interrupter(OverlapActs):
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
        confirming: Confirming,
    ) -> None:
        self._commands, self._speaker, self._turns = commands, speaker, turns
        self._sync, self._confirming = sync, confirming
        self._usage, self._recorder, self._events = books.usage, books.recorder, books.events
        self._over, self._answer = over, answer
        self._two_step = setup.settings.interruptions.mode == "two_step"
        self._own_s = setup.settings.interruptions.own_words_s
        self._overlaps = Overlaps(setup, confirming=confirming)
        min_words, words = setup.settings.interruptions.min_words, self._overlaps.words
        self._follows = Follows(
            speaker=speaker, turns=turns, over=over, answer=answer, words=words, min_words=min_words
        )
        self._talker = setup.talker is not None
        self.asks = OverlapAsks(setup, books, guarded=guarded, over=over, decide=self.model_said)
        self._held: dict[TurnId, tuple[TurnLog, HeardWords | None, Transcribed]] = {}
        self.yes_over = YesOverQuestion(
            setup,
            speaker.playback,
            turns=turns,
            follows=self._follows,
            answer=answer,
            guarded=guarded,
            sync=sync,
        )

    async def opened(self, event: TurnOpened, over: Reply) -> None:
        """The turn `event` opens is an overlap of `over`: the agent's voice lowered, and the
        overlap's transcripts asked for."""
        turn_id, at = event.turn_id, event.at
        self._turns.turn(turn_id).over_reply = over.reply_id
        commands = self._overlaps.open(turn_id, reply_id=over.reply_id, speech_at=event.speech_at)
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
        if event.turn_id in self._follows.repeats:
            await self._follows.follow(state, event.at)
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
        any other is answered, as under `drop`. While confirming, a whole stop or pause request
        declines the read-back, the talker asking what to change (the owner's stop ruling)."""
        self.yes_over.heard(turn, heard, event, answered=True)
        command = None if self._over() else self.command(heard)
        if command == "stop" and self._confirming.active:
            self._confirming.decline(turn.turn_id, "stopped")
            command = None
        read_back = self._confirming.read_back if command == "repeat" else None
        if command is None or (command == "repeat" and self._talker and read_back is None):
            await self._answer(turn, heard, event)
            return
        self._recorder.line(event.at, "command", turn_id=turn.turn_id, command=command)
        await self._stop_earlier(turn, command, event.at)
        if read_back is not None:
            await self._read_again(turn, read_back.plan, event.at)
        elif command == "repeat":
            await self._follows.repeat(turn, event.at)
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
        request that speech followed, what followed read (overlap_follow.py). With a talker, the
        talker's (`_hand_over`)."""
        state = self._overlaps.get(turn.turn_id)
        if self._talker:
            await self._hand_over(state, turn, heard, event)
            return
        if state is not None and state.reads_on:
            await self._follows.read_on(state, turn, heard, event)
            return
        decided = await self._judged_again(state, turn, event)
        if state is not None and turn.turn_id in self._follows.repeats:
            await self._follows.follow(state, event.at)
        if decided is None or answers(decided) or (state is not None and state.instead):
            await self._answer(self._follows.pending(turn), heard, event)
        else:
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
        whole overlap held after its window's stop or repeat request (`OverlapState.instead`).
        A turn the reply went on over is answered only when it is the yes rule's
        (read_back_heard.py's `takes`): its speech begun once the summary played (a bare yes
        over the closing question), or a yes held over the summary (held_yes.py); else a yes
        over a reply's closing question may be held until the reply ends (D-116, `flush`), and
        every other turn's words are told to it, which may let one go."""
        decided = await self._judged_again(state, turn, event)
        if decided is not None and decided.action == "go_on":
            if heard is not None and takes(self._confirming, heard.speech_at, over=turn.over_reply):
                self.yes_over.heard(turn, heard, event, answered=True)
                await self._answer(self._follows.pending(turn), heard, event)
                return
            played = () if state is None else self._played(state)
            self.yes_over.went_on(turn, heard, event, decided, played)  # held, or settled
            return
        self.yes_over.heard(turn, heard, event, answered=True)
        answered = decided is None or answers(decided) or (state is not None and state.instead)
        failed = event.failure is not None and answered
        plan = None if answered else self._confirming.again(turn.turn_id)
        if plan is not None:
            await self._read_again(turn, plan, event.at)
        stop = heard is not None and self.command(heard) == "stop"
        stop = stop and not self._confirming.declines(turn.turn_id)  # a read-back's: answered
        if plan is not None or (state is not None and not failed and (heard is None or stop)):
            self._turns.ended(turn, "command")
            self._turns.settle(turn)
            return
        await self._answer(self._follows.pending(turn), heard, event)

    async def flush(self, at: float) -> None:
        """After each step of the session's, at `at`: each yes held over a closing question
        answered or let go once due (yes_over_question.py's), quiet when no words are on the way."""
        quiet = self._turns.all_heard and not self._overlaps.open_turns and not self._held
        await self.yes_over.flush(at, quiet=quiet)

    def receipt(self, speech_at: float | None, *, quiet: bool = False) -> ReadBackReceipt | None:
        """The current read-back's receipt, built now, for a turn whose speech began at
        `speech_at` (read_back.py's `Confirming.receipt`): when the yes rule is called; with
        `quiet`, None while any overlap of the call is undecided (a held yes's: held_yes.py)."""
        if quiet and self._overlaps.open_turns:
            return None
        return self._confirming.receipt(speech_at=speech_at, undecided=self._overlaps.undecided)
