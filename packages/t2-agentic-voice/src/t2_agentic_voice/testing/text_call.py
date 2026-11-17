"""`TextCall` (the design's 9.2; plans 006 and 007): a call held in text, for a team's tests and the
library's. It runs the real voice session (voice/session/), the real talker, tools and output
guard, and for an agent with actions the real action runner, yes rule and outbox, in memory
unless the test gives one (`outbox`), with no audio: each of the caller's turns is typed text
standing in for heard words (their source `typed`, which the yes rule takes only under
`env="test"`), the agent's speech is a fake text-to-speech whose clauses play at
`chars_per_second`, and time is a virtual clock that moves only when the test says (`advance`).
It needs no key and no network, never starts Pipecat, and is deterministic; it always runs with
`env="test"`, and writes its call's report under a folder of its own, never a team's `var/`. It
is not a chat channel. The model is the test's (`ScriptedLLM`, `FunctionLLM`:
testing/llm_fakes.py, or a real one through its port for a measurement), and so is every
tool's and action's backend (`FakeKnowledgeBase` for the knowledge tool). An agent that
declares no instructions runs the echo, as in a call.

**The clock.** The session, the talker and the tool runner all run on the call's one clock
(core/clock.py), and so does a `ScriptedLLM` or `FunctionLLM` given as the model (its `clock`,
set as each call starts, so a fake reused across calls never waits on an earlier call's), so
`advance` brings a model's pause, a tool's progress line, its timeout and the words said
`at="tool_running"` when they are due and not before. A measurement with a real model runs on
the system clock instead (`clock="system"`), so its turns' times are real ones, and `advance`
then waits that long. What moves the clock, waits for an injection's moment (at most
`MAX_WAIT_S`) and lets the session go quiet is testing/text_side.py's `TextDriver`.

**Injections:** `call.user(text)`, a turn said while the agent is silent (the clock moves on
first until the reply playing has ended, and past the 300 ms after it that would make the turn
an overlap); `call.user(text, during="agent_speaking")`, said over the reply playing (the clock
moves on until one plays); `during="read_back"` or `"closing_question"`, said over a
read-back's summary or its closing question as it plays (testing/text_read_back.py);
`call.user(text, at="tool_running")`, said while a tool of a reply runs (until one does);
`call.advance(seconds)`; `call.stop()`, the client's Stop. A turn's speech takes `len(text) /
chars_per_second` seconds and the speech detector's stop delay (`turns.vad_stop_ms`), the reply
playing on under it; its transcript then comes at once, an overlap's whole overlap part first,
which the turn's own reuses (io.py's overlaps). `user` returns once what the turn's words start
has run as far as it can with the clock still: on the virtual clock, its reply asked for as far
as the talker could write it, its clauses still to play as the clock moves; on the system clock,
once its reply is written whole (or stopped). A read-back plays whole unless the test arms a
fault for the next one (`fault_read_back`): its summary cut short, with no audio, or failed.

**Expectations**, on each turn's `expect`: `tool_call(name, **args)`, `said(contains=)` (the
reply as the caller heard it, or is still to hear it when no stop cut it), `blocked()`,
`cancelled(tool)` and `language(tag)`, and an action's, `read_back(contains=, **values)`,
`no_read_back()`, `asked_again()`, `confirmed(name, **values)`, `no_action()`,
`action_ended(name, kind)` and `action_completed(name)` (testing/text_actions.py), each raising
AssertionError with what the turn did instead. An AssertionError the talker raises (a fake model
whose script ran out) is raised by the next `user`, `advance`, `stop` or the call's end, never
heard as the `error` notice only. `call.violations` holds the output guard's checks, rules A to
C, and the yes rule's, run on everything the talker said and every action confirmed
(testing/text_checks.py).

**What a turn did**, as data, for a runner that scores the call rather than asserts on it
(testing/turn_data.py): its fate, the clauses the caller heard with their languages, the tool
calls with their arguments, the cards, the blocked clauses, the times to the first token and the
first clause, the model requests and their usage (testing/text_turn.py); its events, `emitted`.
"""

from __future__ import annotations

import tempfile
from datetime import date
from types import TracebackType
from typing import Literal, Self

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.agent_tools import action_runner, actions_of, talker_tools
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.agent.talker import Talker, TalkerCall, talker_factory
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.outbox import Outbox
from t2_agentic_voice.testing import text_moments, text_parts
from t2_agentic_voice.testing.llm_fakes import FunctionLLM, ScriptedLLM
from t2_agentic_voice.testing.text_checks import call_violations
from t2_agentic_voice.testing.text_moments import At, During
from t2_agentic_voice.testing.text_parts import CALL_ID, hand_typed, text_session, text_settings
from t2_agentic_voice.testing.text_read_back import part_at, readings
from t2_agentic_voice.testing.text_reads import TextReads, TurnSaid
from t2_agentic_voice.testing.text_side import ClauseFault, TextDriver, TextSide
from t2_agentic_voice.testing.text_turn import TextTurn, TurnExpectations
from t2_agentic_voice.testing.text_watch import (
    RecordingJobs,
    RecordingRunner,
    WatchedTalker,
    plans_of,
)
from t2_agentic_voice.voice.protocol import Hangup, Stop
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.session_events import Connected, FromClient

__all__ = ["TextCall", "TextTurn", "TurnExpectations"]

# The clock a call runs on: virtual, moved only by `advance`, or the system's (a measurement's).
ClockKind = Literal["virtual", "system"]
# The fake text-to-speech's pace for each clause: about 15 characters a second, a calm one.
CHARS_PER_SECOND = 15.0
_OUTSIDE = "A text call is used inside `async with`. FIX: enter it first."


class TextCall:
    """A call of `agent` held in text (the module's docstring), its talker on `llm`; each of
    `settings` (`env` test, the library's defaults), `caller` (a made-up one), `language` (the
    agent's first), `clock` (virtual, or `system`), `today` (in the agent's time zone) and
    `outbox` (in memory) as given, else as said. Enter it (`async with`) to connect, greeted."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        llm: ChatModel,
        settings: VoiceSettings | None = None,
        caller: Caller | None = None,
        language: LanguageTag | None = None,
        chars_per_second: float = CHARS_PER_SECOND,
        clock: ClockKind = "virtual",
        outbox: Outbox | None = None,
        today: date | None = None,
    ) -> None:
        self.agent, self.llm, self.settings = agent, llm, settings
        self.caller, self.language, self.chars_per_second = caller, language, chars_per_second
        self.clock, self.today = clock, today
        self.outbox: Outbox = outbox if outbox is not None else MemoryOutbox()
        self._said: dict[int, TurnSaid] = {}
        self._emitted: list[Event] = []
        self._next_turn = 0
        self._watched: WatchedTalker | None = None
        self._runner: RecordingRunner | None = None
        self._jobs: RecordingJobs | None = None
        self._actions: ActionRunner | None = None
        self._record: ActionRecord | None = None
        self._fault: ClauseFault | None = None
        self._folder: tempfile.TemporaryDirectory[str] | None = None
        self._session: CallSession | None = None
        self._side: TextSide | None = None
        self._driver: TextDriver | None = None
        self._time: Clock = SYSTEM_CLOCK

    def _talker(self, call: TalkerCall, settings: VoiceSettings, clock: Clock) -> Talker:
        """The call's talker, built as the runtime builds it (agent/talker.py's `talker_factory`):
        the test's model, the tools through the recording runner, and the actions' runner."""
        build = talker_factory(self.agent, settings, self.llm, self._actions, runner=self._runner)
        return build(call, clock)

    async def __aenter__(self) -> Self:
        settings, self._folder = text_settings(self.settings)
        clock = text_parts.text_clock(self.clock == "virtual", self.today, self.agent.zone)
        self._time = clock
        if isinstance(self.llm, ScriptedLLM | FunctionLLM):
            self.llm.clock = clock  # this call's, whatever an earlier call set
        caller = self.caller or Caller(subject="text-call")
        language = self.agent.call_language(self.language, locale=caller.locale)
        agent = self.agent
        if actions_of(agent):  # the part that acts, as the runtime gives it
            self._record = ActionRecord()
            self._actions = action_runner(agent, settings, outbox=self.outbox, record=self._record)
            self._jobs = RecordingJobs(self._actions)
        talker: WatchedTalker | None = None
        mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
        if mode == "talker":
            call = TalkerCall(call_id=CALL_ID, caller=caller, language=language.tag)
            self._runner = RecordingRunner(talker_tools(agent, settings))
            self._watched = talker = WatchedTalker(self._talker(call, settings, clock), clock)
        side = self._side = TextSide(clock, chars_per_second=self.chars_per_second)
        side.fault = self._faulted
        self._driver = TextDriver(side, clock)
        self._session = text_session(
            agent,
            settings=settings,
            caller=caller,
            language=language,
            clock=clock,
            side=side,
            talker=talker,
            llm=self.llm,
            jobs=self._jobs,
            emit=self._emitted.append,
        )
        side.start(self._session)
        side.hand(Connected(at=clock.now()))
        await self._drive().quiet()
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        side, session = self._parts()
        if side.ended is None:
            side.hand(FromClient(message=Hangup(v=1, type="hangup"), at=self._time.now()))
            await self._drive().quiet()
        await session.aclose()
        await side.aclose()
        if self._folder is not None:
            self._folder.cleanup()
        if error is None:
            self._failed()

    def _failed(self) -> None:
        """Raise, once, the AssertionError the talker raised (a fake model's script that ran
        out), so the test fails there and never passes on the `error` notice said for it."""
        if self._watched is not None and (failure := self._watched.failure) is not None:
            self._watched.failure = None
            raise failure

    def _parts(self) -> tuple[TextSide, CallSession]:
        if self._side is None or self._session is None:
            raise RuntimeError(_OUTSIDE)
        return self._side, self._session

    def _drive(self) -> TextDriver:
        """What moves the call's clock and lets its session go quiet (text_side.py's)."""
        if self._driver is None:
            raise RuntimeError(_OUTSIDE)
        return self._driver

    async def user(
        self, text: str, *, during: During | None = None, at: At | None = None
    ) -> TextTurn:
        """The caller says `text`: while the agent is silent, or `during` its reply or a part
        of a read-back, or `at` a point of a reply; returns once what its words start has run
        as far as it can (the module's injections)."""
        side, session = self._parts()
        reads = self._reads()
        await self._drive().until(*text_moments.moment(reads, during, at, now=self._time.now))
        turn_id = self._next_turn
        self._next_turn += 1
        self._said[turn_id] = await hand_typed(
            side,
            session,
            self._drive(),
            self._time,
            turn_id=turn_id,
            text=text,
            chars_per_second=self.chars_per_second,
        )
        await self._drive().quiet()
        if self.clock == "system":
            written = "the turn's reply was never written"
            await self._drive().until(lambda: text_moments.written(reads, turn_id), written)
        self._failed()
        return TextTurn(reads, turn_id)

    async def advance(self, seconds: float) -> None:
        """Move the virtual clock `seconds` on, what is due by then done (system clock: wait)."""
        self._parts()
        await self._drive().advance(seconds)
        self._failed()

    async def stop(self) -> None:
        """The client's Stop: the agent's speech stops at once, and the reply's work with it."""
        side, _ = self._parts()
        side.hand(FromClient(message=Stop(v=1, type="stop"), at=self._time.now()))
        await self._drive().quiet()
        self._failed()

    def fault_read_back(self, fault: ClauseFault) -> None:
        """Arm a fault for the next read-back's summary to play: its first clause to end comes
        back cut short (`cut_short`), with no audio (`no_audio`), or failed (`failed`), so the
        summary never plays whole."""
        self._fault = fault

    def _faulted(self, speak: Speak) -> ClauseFault | None:
        """The armed fault, once, for a clause of a read-back's summary (the side asks as each
        clause ends); None for any other clause."""
        if self._fault is None or self._session is None:
            return None
        found = readings(self._session.playback, plans_of(self._watched))
        if part_at(found, speak.reply_id, speak.clause) != "summary":
            return None
        fault, self._fault = self._fault, None
        return fault

    @property
    def violations(self) -> tuple[str, ...]:
        """What the call's checks found so far (testing/text_checks.py), each said in words."""
        return call_violations(self._reads(), year=self._time.wall().year)

    @property
    def emitted(self) -> tuple[Event, ...]:
        """The call's public events so far, in order, as the runtime's observers get them."""
        return tuple(self._emitted)

    def _reads(self) -> TextReads:
        side, session = self._parts()
        return TextReads(
            session=session,
            side=side,
            said=self._said,
            watched=self._watched,
            runner=self._runner,
            jobs=self._jobs,
            record=self._record,
        )
