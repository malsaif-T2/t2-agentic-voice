"""The talker as the voice session sees it (plan 006): one turn in, a stream of events out, run in
the reply's cancel scope.

**In:** a `TalkerTurn` (core/conversation.py), which the session builds from its heard history:
the turn's heard words, whole, the language its transcript was heard in, the reply it was said
over and the reply it cut, and the call so far as the caller heard it, clause by clause (an
unplayed clause never reaches the model as said; a cut one is marked cut, with its share). The
talker of one call is built for it (`TalkerCall`: the call's id, its verified caller, its
language) and keeps what the history does not hold between turns: its tool calls and results,
its developer notes, and the evidence its tools gave the output guard.

**Out:** events the session plays in order, as they come (agent/events.py, each re-exported
here): a clause to speak (`SpokenClause`, in the reply's language, each whole once the model has
written it, so the first is spoken while the model still writes); a card to show (`ShownCard`);
a tool begun and ended (`ToolBegan`, `ToolEnded`); the progress line of a tool that has one
(`ProgressDue`, said by the session from the phrase cache if the wait runs long); a clause
the output guard blocked (`ClauseBlocked`, never spoken: the session speaks the presets'
`error` notice in its place and emits `GuardBlocked` with its `reason`, and the talker keeps a
developer note); an action's read-back to say (`ReadBackRequested`, the reply's last event
before its end: the session reads it back and asks; nothing the talker gives confirms it);
the reply moved into another of the agent's languages by the `switch_language` tool
(`LanguageMoved`, after the tool's result: its later clauses in that language, and the
session moves the call); each model request as it goes and as it ends (`ModelRequested`,
`ModelReplied`, for the call's usage and the turn's times); and the reply's end (`ReplyDone`),
after its last clause and its work, with how many of the talker's clauses it left unsaid once it
stopped before a question past its limit (`unsaid_clauses`, agent/question_limit.py, D-085). A
`ProviderError` from the model is raised from the stream instead, after any clause already
given, for the session to say the `error` notice: no event says it.

**A clause's length.** The talker cuts the model's text with the clause splitter at no limit,
for it knows no voice: the session fits each clause to the voice's `max_chars` once it has said
the clause's digits by the speaking rules (`speak_digits`, which lengthens it) and applied the
pronunciation map, keeping the clause as written for its caption.

**The scope** (D-060). The session iterates `Talker.reply` in a task it starts in the reply's
cancel scope (voice/session/scope.py's `CancelScope`, which `ReplyScope` describes), so a stop
cancels the model's request, the search and the speech at once. Work the talker runs beside the
stream (a tool) starts in the same scope, but for a tool whose barge-in is `finish`. A cancel
ends the stream at once, with no `ReplyDone`.

**The clock.** The talker keeps its times on the call's clock (core/clock.py's `Clock`, the one
the session runs on: `SYSTEM_CLOCK` in a call, `TextCall`'s virtual clock in a test), never on
asyncio's own time or the system's: the tool's timeout (the runner's `run` takes the clock), a
tool's `ms`, a request's `first_token_s`, and the prompt's date (`compose_prompt`'s `today`, the
date of `clock.wall()`). So a test that moves its clock on brings what is due by then, and only
that.

**Built for each call** by one factory of a call's `ChatTalker` (`talker_factory`), which the
runtime (api/runtime.py) and the audio call (testing/audio_call.py) reach through
`chat_talkers`, and the text call (testing/text_call.py) directly: the agent's mode, read under
the settings' prefix (`session.mode_for`), says whether its calls run the talker; one tool
runner of the talker's tools serves every call, and so does the agent's action runner, when it
declares actions.

What one reply does, request by request, is agent/turn.py's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Protocol

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.agent_tools import talker_tools
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.agent.events import (
    ClauseBlocked,
    LanguageMoved,
    ModelReplied,
    ModelRequested,
    ProgressDue,
    ReadBackRequested,
    ReplyDone,
    ReplyScope,
    ShownCard,
    SpokenClause,
    TalkerEvent,
    ToolBegan,
    ToolEnded,
    _Event,
)
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.agent.turn import Turn
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel

__all__ = [
    "ChatTalker",
    "ClauseBlocked",
    "LanguageMoved",
    "ModelReplied",
    "ModelRequested",
    "ProgressDue",
    "ReadBackRequested",
    "ReplyDone",
    "ReplyScope",
    "ShownCard",
    "SpokenClause",
    "Talker",
    "TalkerCall",
    "TalkerEvent",
    "ToolBegan",
    "ToolEnded",
    "chat_talkers",
    "talker_factory",
]


class TalkerCall(_Event):
    """The call a talker is built for: its id, its verified caller, and its language, fixed at
    join (`VoiceAgent.call_language`)."""

    call_id: CallId
    caller: Caller
    language: LanguageTag


class Talker(Protocol):
    """One call's talker, as the session calls it (the module's docstring)."""

    def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        """The reply to `turn`, event by event, ending with `ReplyDone` unless cancelled."""
        ...


class ChatTalker:
    """The library's talker for one call (`call`): `agent`'s instructions and tools, the chat
    `model` and the tool `runner` the api layer injects, the `settings` (`llm`, `guard`), and
    the call's `clock`, the session's, that it keeps its times on (the module's docstring); and
    `actions`, the agent's action runner when it declares actions, one for every call, whose
    record of this call (`record`) its jobs add to and the output guard reads. A `Talker`; one
    reply at a time."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        model: ChatModel,
        runner: ToolRunner,
        settings: VoiceSettings,
        call: TalkerCall,
        clock: Clock,
        actions: ActionRunner | None = None,
    ) -> None:
        self.agent, self.model, self.runner = agent, model, runner
        self.settings, self.call, self.clock = settings, call, clock
        self.actions = actions
        self.record = None if actions is None else actions.record(call.call_id)
        self._memory = Memory()

    def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        """The reply to `turn` (the module's docstring; agent/turn.py)."""
        run = Turn(
            self.agent,
            model=self.model,
            runner=self.runner,
            settings=self.settings,
            clock=self.clock,
            caller=self.call.caller,
            call_id=self.call.call_id,
            call_language=self.call.language,
            memory=self._memory,
            turn=turn,
            scope=scope,
            actions=self.actions,
            record=self.record,
        )
        return run.events()


def chat_talkers(
    agent: VoiceAgent,
    settings: VoiceSettings,
    chat: ChatModel | None,
    actions: ActionRunner | None = None,
    *,
    runner: ToolRunner | None = None,
) -> Callable[[TalkerCall, Clock], Talker] | None:
    """The factory of each call's talker (the module's docstring), `talker_factory`'s on
    `chat`; None for an agent whose calls run the echo, or with no chat model (voice's entry
    point then refuses an agent that runs the talker, saying so). A ConfigurationError naming
    `session.mode` under the settings' prefix when it is talker for an agent with no
    instructions."""
    mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    if mode != "talker" or chat is None:
        return None
    return talker_factory(agent, settings, chat, actions, runner=runner)


def talker_factory(
    agent: VoiceAgent,
    settings: VoiceSettings,
    model: ChatModel,
    actions: ActionRunner | None = None,
    *,
    runner: ToolRunner | None = None,
) -> Callable[[TalkerCall, Clock], Talker]:
    """The factory of each call's `ChatTalker` of an agent whose calls run the talker: on
    `model`, with `runner` (one of the talker's tools unless given: actions/agent_tools.py's
    `talker_tools`) and `actions`, the agent's action runner, for every call."""
    tools = runner if runner is not None else ToolRunner(talker_tools(agent, settings))

    def build(call: TalkerCall, clock: Clock) -> Talker:
        return ChatTalker(
            agent,
            model=model,
            runner=tools,
            settings=settings,
            call=call,
            clock=clock,
            actions=actions,
        )

    return build
