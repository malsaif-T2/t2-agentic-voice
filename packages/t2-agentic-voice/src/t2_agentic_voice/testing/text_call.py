"""`TextCall` (the design's 9.2; plan 006): a call held in text, for a team's tests and the
library's. It runs the real voice session (voice/session/), the real talker, tools and output
guard, with no audio: each of the caller's turns is typed text standing in for heard words, the
agent's speech is a fake text-to-speech whose clauses play at `chars_per_second`, and time is a
virtual clock that moves only when the test says (`advance`). It needs no key and no network,
never starts Pipecat, and is deterministic; it always runs with `env="test"`, the only place
typed text stands in for heard words, and writes its call's report under a folder of its own,
never a team's `var/`. It is not a chat channel. The model is the test's (`ScriptedLLM`,
`FunctionLLM`: testing/llm_fakes.py, or a real one through its port for a measurement), and so
is every tool's backend (`FakeKnowledgeBase` for the knowledge tool). An agent that declares no
instructions runs the echo, as in a call.

**The clock.** The session, the talker and the tool runner all run on the call's one clock
(core/clock.py), and so does a `ScriptedLLM` or `FunctionLLM` given as the model (its `clock`,
set as each call starts, so a fake reused across calls never waits on an earlier call's), so
`advance` brings a model's pause, a tool's progress line, its timeout and the words said
`at="tool_running"` when they are due and not before. A measurement with a real model runs on
the system clock instead (`clock="system"`), so its turns' times are real ones, and `advance`
then waits that long.

**Injections:** `call.user(text)`, a turn said while the agent is silent (the clock moves on
first until the reply playing has ended, and past the 300 ms after it that would make the turn
an overlap); `call.user(text, during="agent_speaking")`, said over the reply playing (the clock
moves on until one plays); `call.user(text, at="tool_running")`, said while a tool of a reply
runs (until one does); `call.advance(seconds)`; `call.stop()`, the client's Stop. A turn's
speech takes `len(text) / chars_per_second` seconds and the speech detector's stop delay
(`turns.vad_stop_ms`), the reply playing on under it; its transcript then comes at once, an
overlap's whole overlap part first, which the turn's own reuses (io.py's overlaps). `user`
returns once what the turn's words start has run as far as it can with the clock still: on the
virtual clock, its reply asked for as far as the talker could write it, its clauses still to
play as the clock moves; on the system clock, once its reply is written whole (or stopped).

**Expectations**, on each turn's `expect`: `tool_call(name, **args)`, `said(contains=)` (the
reply as the caller heard it, or is still to hear it when no stop cut it), `blocked()`,
`cancelled(tool)` and `language(tag)`, each raising AssertionError with what the turn did
instead. An AssertionError the talker raises (a fake model whose script ran out) is raised by
the next `user`, `advance`, `stop` or the call's end, never heard as the `error` notice only.
`call.violations` holds the output guard's checks (rule B, domain/guard.py), run on
every clause the talker said, against the caller's words, the tools' evidence and the cards.

**What a turn did**, as data, for a runner that scores the call rather than asserts on it
(testing/turn_data.py): its fate, the clauses the caller heard with their languages, the tool
calls with their arguments, the cards, the blocked clauses, the times to the first token and the
first clause, and the model requests and their usage (testing/text_turn.py).
"""

from __future__ import annotations

import asyncio
import dataclasses
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.agent.talker import ChatTalker, Talker, TalkerCall, ToolBegan, ToolEnded
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.guard import check_ids
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.testing.llm_fakes import FunctionLLM, ScriptedLLM
from t2_agentic_voice.testing.text_side import TextPhrases, TextSide, VirtualClock, settle
from t2_agentic_voice.testing.text_turn import TextReads, TextTurn, TurnExpectations, TurnSaid
from t2_agentic_voice.testing.text_watch import RecordingRunner, WatchedTalker, tools_of
from t2_agentic_voice.voice.protocol import Hangup, Stop
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S
from t2_agentic_voice.voice.session.session_events import (
    Connected,
    FromClient,
    Transcribed,
    Transcribing,
    TranscriptPart,
    TurnClosed,
    TurnOpened,
)

__all__ = ["TextCall", "TextTurn", "TurnExpectations"]

# When a turn is said: over the reply playing.
During = Literal["agent_speaking"]
# Where in a reply a turn is said: while one of its tools runs.
At = Literal["tool_running"]
# The clock a call runs on: a virtual one, moved only by `advance`; or the system's, for a
# measurement with a real model.
ClockKind = Literal["virtual", "system"]
# The pace the fake text-to-speech plays each clause at: about 15 characters a second, a calm
# speaking rate.
CHARS_PER_SECOND = 15.0
# The most characters a text call's text-to-speech request takes: Orpheus's (the design's 3.1).
MAX_CHARS = 200
# The call's ID, and the most a wait for an injection's moment moves the clock (on the system
# clock, waits) before it gives up, saying so: the agent's bound, past any reply of a test's.
CALL_ID = "text-call"
MAX_WAIT_S = 120.0
# The longest step a wait for an injection's moment moves the virtual clock, so it stops soon
# after the moment comes, even when no sleep ends then (the drop rule's tail after a reply).
WAIT_STEP_S = 0.05
# The turns of the event loop a text call lets pass, at most, for its session to go quiet.
_QUIET_ROUNDS = 200


class TextCall:
    """A call of `agent` held in text (the module's docstring), its talker on `llm`, with
    `settings` (`env` test, the library's defaults, unless given), its caller `caller` (a made-up
    one unless given) in `language` (the agent's first unless given), on `clock` (a virtual one
    unless `system` is given). Enter it (`async with`) to connect the call, greeted; leaving it
    hangs up."""

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
    ) -> None:
        self.agent, self.llm, self.settings = agent, llm, settings
        self.caller, self.language, self.chars_per_second = caller, language, chars_per_second
        self.clock = clock
        self._said: dict[int, TurnSaid] = {}
        self._emitted: list[Event] = []
        self._next_turn = 0
        self._watched: WatchedTalker | None = None
        self._runner: RecordingRunner | None = None
        self._folder: tempfile.TemporaryDirectory[str] | None = None
        self._session: CallSession | None = None
        self._side: TextSide | None = None
        self._time: Clock = SYSTEM_CLOCK

    def _talker(self, call: TalkerCall, settings: VoiceSettings, clock: Clock) -> Talker:
        """The call's talker: the library's, on the test's model and the agent's tools."""
        runner: ToolRunner = self._runner or ToolRunner(tools_of(self.agent))
        return ChatTalker(
            self.agent, model=self.llm, runner=runner, settings=settings, call=call, clock=clock
        )

    async def __aenter__(self) -> Self:
        settings = self.settings or VoiceSettings(env="test")
        if settings.env != "test":
            raise ConfigurationError(
                f"A text call runs under env=test, not env={settings.env}: only there may typed "
                "text stand in for heard words. FIX: give it settings with env='test'."
            )
        self._folder = tempfile.TemporaryDirectory(prefix="t2v-text-call-")
        storage = StorageSettings(var_dir=Path(self._folder.name))
        settings = settings.model_copy(update={"storage": storage})
        clock: Clock = VirtualClock() if self.clock == "virtual" else SYSTEM_CLOCK
        self._time = clock
        if isinstance(self.llm, ScriptedLLM | FunctionLLM):
            self.llm.clock = clock  # this call's, whatever an earlier call set
        caller = self.caller or Caller(subject="text-call")
        language = self.agent.call_language(self.language, locale=caller.locale)
        talker: Talker | None = None
        if settings.session.mode_for(instructed=self.agent.instructed) == "talker":
            call = TalkerCall(call_id=CALL_ID, caller=caller, language=language.tag)
            self._runner = RecordingRunner(tools_of(self.agent))
            self._watched = talker = WatchedTalker(self._talker(call, settings, clock), clock)
        side = self._side = TextSide(clock, chars_per_second=self.chars_per_second)
        setup = CallSetup(
            call_id=CALL_ID,
            caller=caller,
            consent=Consent(version=None, record_audio=False),
            agent=self.agent,
            language=language,
            settings=settings,
            phrases=TextPhrases(self.agent),
            max_chars=lambda tag: MAX_CHARS,
            tracing=Tracing(),
            emit=self._emitted.append,
            clock=clock,
            talker=talker,
        )
        self._session = CallSession(setup, side)
        side.start(self._session)
        side.hand(Connected(at=clock.now()))
        await self._quiet()
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
            await self._quiet()
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
            raise RuntimeError("A text call is used inside `async with`. FIX: enter it first.")
        return self._side, self._session

    async def user(
        self, text: str, *, during: During | None = None, at: At | None = None
    ) -> TextTurn:
        """The caller says `text`: while the agent is silent, or `during` its reply, or `at` a
        point of it; returns once what its words start has run as far as it can (the module's
        injections)."""
        side, session = self._parts()
        if at == "tool_running":
            await self._until(self._tool_running, "no tool of a reply ran")
        elif during == "agent_speaking":
            await self._until(lambda: session.playback.speaking, "no reply played")
        else:
            await self._until(self._silent, "the agent was never silent")
        turn_id, start = self._next_turn, self._time.now()
        self._next_turn += 1
        side.hand(TurnOpened(turn_id=turn_id, at=start, speech_at=start))
        await self._quiet()
        speech_s = max(len(text), 1) / self.chars_per_second
        await self._advance(speech_s + session.setup.settings.turns.vad_stop_ms / 1000)
        end = self._time.now()
        heard = Transcript(text=text, language=session.setup.language.primary)
        own = Transcribed(turn_id=turn_id, at=end, audio_s=speech_s, sent_at=end, transcript=heard)
        closed = TurnClosed(turn_id=turn_id, at=end, speech_ended_at=end)
        if turn_id in side.overlaps:
            part: TranscriptPart = "overlap"
            side.hand(Transcribing(turn_id=turn_id, at=end, audio_s=speech_s, part=part))
            side.hand_all([dataclasses.replace(own, part=part), closed, own])
        else:
            side.hand_all([closed, Transcribing(turn_id=turn_id, at=end, audio_s=speech_s), own])
        self._said[turn_id] = TurnSaid(turn_id=turn_id, text=text, handed_at=end)
        await self._quiet()
        if self.clock == "system":
            await self._until(lambda: self._written(turn_id), "the turn's reply was never written")
        self._failed()
        return TextTurn(self._reads(), turn_id)

    async def advance(self, seconds: float) -> None:
        """Move the call's virtual clock `seconds` on, what is due by then done (on the system
        clock, wait `seconds`)."""
        self._parts()
        await self._advance(seconds)
        self._failed()

    async def stop(self) -> None:
        """The client's Stop: the agent's speech stops at once, and the reply's work with it."""
        side, _ = self._parts()
        side.hand(FromClient(message=Stop(v=1, type="stop"), at=self._time.now()))
        await self._quiet()
        self._failed()

    @property
    def violations(self) -> tuple[str, ...]:
        """What the output guard's checks found in the call so far, each said in words."""
        _, session = self._parts()
        reads = self._reads()
        evidence = [said.text for said in self._said.values()]
        evidence += list(self._runner.evidence if self._runner is not None else ())
        for turn_id in self._said:
            for card in TextTurn(reads, turn_id).cards:
                evidence += [card.title, *card.steps, *([card.source] if card.source else [])]
        found: list[str] = []
        year = self._time.wall().year
        for turn_id in self._said:
            for clause in TextTurn(reads, turn_id).clauses:
                if clause.phrase or clause.fate == "unplayed":
                    continue
                verdict = check_ids(
                    clause.text, evidence=evidence, settings=session.setup.settings.guard, year=year
                )
                if not verdict.passed:
                    tokens = ", ".join(verdict.unsupported)
                    found.append(f"turn {turn_id} said {tokens} with no evidence: {clause.text!r}")
        return tuple(found)

    def _reads(self) -> TextReads:
        side, session = self._parts()
        return TextReads(
            session=session,
            side=side,
            said=self._said,
            watched=self._watched,
            runner=self._runner,
        )

    def _silent(self) -> bool:
        """Whether the agent is silent: no reply in progress, and the last past its tail."""
        _, session = self._parts()
        playback = session.playback
        if playback.in_progress():
            return False
        ended = [r.ended_at for r in (playback.reply(i) for i in range(playback.next_id)) if r]
        last = max((at for at in ended if at is not None), default=None)
        return last is None or self._time.now() > last + DROP_AFTER_S

    def _tool_running(self) -> bool:
        """Whether a tool of a reply still in progress runs now."""
        if self._watched is None:
            return False
        for talk in self._watched.talks.values():
            ended = {e.call_id for _, e in talk.events if isinstance(e, ToolEnded)}
            began = [e for _, e in talk.events if isinstance(e, ToolBegan)]
            if not talk.cancelled and any(e.call_id not in ended for e in began):
                return True
        return False

    def _written(self, turn_id: int) -> bool:
        """Whether the turn's reply is written whole, stopped, or none answers it."""
        _, session = self._parts()
        fate = next((t.fate for t in session.history.turns() if t.turn_id == turn_id), "pending")
        replies = [r for r in session.history.replies() if r.turn_id == turn_id]
        if fate != "pending" or not replies:
            return fate != "pending" or self._watched is None
        reply = session.playback.reply(replies[-1].reply_id)
        return reply is None or not reply.open or reply.ended_at is not None

    async def _until(self, ready: Callable[[], bool], failure: str) -> None:
        """Move the clock on (on the system clock, wait) until `ready()`, at most MAX_WAIT_S;
        AssertionError saying `failure` otherwise."""
        waited = 0.0
        while not ready():
            clock = self._time
            if isinstance(clock, VirtualClock):
                due = clock.next_due
                if waited >= MAX_WAIT_S:
                    raise AssertionError(f"{failure} (the call waited {waited:.1f} s)")
                step = WAIT_STEP_S if due is None else min(max(due - clock.now(), 0.0), WAIT_STEP_S)
                await self._advance(step)
                waited += step
            else:
                await asyncio.sleep(0.02)
                waited += 0.02
                if waited > MAX_WAIT_S:
                    raise AssertionError(f"{failure} (the call waited {waited:.1f} s)")
            await self._quiet()

    async def _advance(self, seconds: float) -> None:
        clock = self._time
        if isinstance(clock, VirtualClock):
            await clock.advance(seconds)
        else:
            await asyncio.sleep(seconds)
        await self._quiet()

    async def _quiet(self) -> None:
        """Let the session take what it was handed, and what that started run, with the clock
        still: until nothing waits for it and nothing was handed or given, three rounds
        running, at most `_QUIET_ROUNDS` rounds."""
        side, _ = self._parts()
        calm, steps = 0, side.steps
        for _ in range(_QUIET_ROUNDS):
            await settle(5)
            moved, steps = side.steps != steps, side.steps
            calm = 0 if side.busy or moved else calm + 1
            if calm >= 3:
                return
