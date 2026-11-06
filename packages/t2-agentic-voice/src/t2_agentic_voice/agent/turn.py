"""One reply of the talker's (agent/talker.py's `ChatTalker.reply`; plan 006): from the caller's
turn and the call as it was heard to the events the session plays, within the reply's scope.

- **The request.** The system prompt in the turn's reply language (agent/prompt.py,
  agent/language.py), the call as the caller heard it with what the talker kept beside it
  (agent/context.py), then the turn, whole. At most `MAX_REQUESTS` a turn: each but the last
  offers the agent's tools, the last none, so the turn ends in words; a tool call the last one
  makes anyway is not run.
- **Speech as it is written.** The model's text goes through the clause splitter as it streams
  (`ClauseStream`), any note of the history's it copied taken out first (agent/context.py's
  `Unnoted`), and each whole clause, once the output guard's rule B passed it against the
  evidence seen this call (its tools' results, the caller's heard words), is yielded at once.
  A blocked one is `ClauseBlocked`, and by `guard.on_block` the rest of the reply goes with it
  (`drop_rest`: no more clause, request or tool) or only it; the next turn's history holds a
  developer note.
- **Tools** (agent/tool_calls.py). Each call the model asks for starts at once, in the reply's
  scope, and runs through the runner; a progress line is due once a tool runs past its
  `progress_after_s` (one a reply); each result goes back to the model framed as data, a
  result's card is shown once the guard passed its text, and the calls and results are kept
  for the call's next `KEPT_TURNS` turns, which the heard history does not hold.
- **Failure and cancel.** A `ProviderError` from the model ends the reply: it is raised from the
  stream after any clause already given, for the session to say the `error` notice. A cancel of
  the reply's scope cancels the task that iterates the stream, so the model's request (its
  stream closed) and every tool of the scope stop at once, and no `ReplyDone` comes.
- **Time** is the call's clock's alone: the progress time, a tool's `ms`, a request's
  `first_token_s` and the prompt's date (the runner times each tool's timeout on it too).
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator, AsyncIterator, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, ToolResult
from t2_agentic_voice.agent.context import BLOCKED, Unnoted, history, turn_message
from t2_agentic_voice.agent.events import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ReplyDone,
    ReplyScope,
    SpokenClause,
    TalkerEvent,
)
from t2_agentic_voice.agent.language import reply_language
from t2_agentic_voice.agent.prompt import compose_prompt
from t2_agentic_voice.agent.tool_calls import Memory, ToolCalls, exchange
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.guard import check_ids
from t2_agentic_voice.domain.ports.chat_model import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
)
from t2_agentic_voice.domain.text.clauses import ClauseStream

_log = get_logger(__name__)
# The most model requests one turn makes; the last offers no tool, so the turn ends in words.
MAX_REQUESTS = 3
# The models that take a reasoning effort (`llm.reasoning_effort`); the others are sent none.
_REASONING = frozenset({"openai/gpt-oss-120b", "openai/gpt-oss-20b"})


@dataclass
class _Answer:
    """What one model request gave: its text, its tool calls, its usage, its first token's
    time."""

    text: str = ""
    calls: list[ToolCallRequest] = field(default_factory=list)
    usage: Usage | None = None
    first_token_s: float | None = None


async def _closed(stream: AsyncIterator[Any]) -> None:
    """Close the model's `stream`, as an async generator closes."""
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        await aclose()


class Turn:
    """One reply of a call's talker (the module's docstring)."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        model: ChatModel,
        runner: ToolRunner,
        settings: VoiceSettings,
        clock: Clock,
        caller: Caller,
        call_id: str,
        call_language: LanguageTag,
        memory: Memory,
        turn: TalkerTurn,
        scope: ReplyScope,
    ) -> None:
        self.agent, self.model, self.runner = agent, model, runner
        self.settings, self.clock, self.memory = settings, clock, memory
        self.turn, self.scope = turn, scope
        spoken = [language.tag for language in agent.languages]
        self.language = reply_language(turn, call=call_language, spoken=spoken)
        self.ctx = CallContext(caller=caller, call_id=call_id, language=self.language)
        self.year = clock.wall().year
        heard = [t.words for t in turn.conversation.turns if t.fate != "dropped" and t.words]
        self.heard = (*heard, turn.words)
        self.stopped = False  # a blocked clause dropped the rest of the reply
        self.blocked = 0
        self.tools = ToolCalls(
            runner=runner,
            ctx=self.ctx,
            clock=clock,
            scope=scope,
            memory=memory,
            turn_id=turn.turn_id,
            shown=self._shown,
        )

    async def events(self) -> AsyncGenerator[TalkerEvent, None]:
        """The reply's events, in order, ending with `ReplyDone` unless cancelled."""
        named = frozenset(r for r in (self.turn.over_reply, self.turn.cut_reply) if r is not None)
        prompt = compose_prompt(self.agent, language=self.language, today=self.clock.wall().date())
        past = history(
            self.turn.conversation,
            exchanges=self.memory.exchanges,
            notes=self.memory.notes,
            named=named,
        )
        messages = [ChatMessage.system(prompt), *past, turn_message(self.turn)]
        requests = tools_run = 0
        for index in range(MAX_REQUESTS):
            tools = self.runner.schemas() if index < MAX_REQUESTS - 1 else ()
            request = self._request(messages, tools)
            requests += 1
            yield ModelRequested(model=request.model)
            answer = _Answer()
            asked = self._asked(request, answer)
            try:
                async for event in asked:
                    yield event
            finally:
                await asked.aclose()
            yield ModelReplied(
                model=request.model, usage=answer.usage, first_token_s=answer.first_token_s
            )
            if self.stopped or not answer.calls:
                break
            if not tools:
                _log.warning("talker_tool_call_ignored", turn_id=self.turn.turn_id)
                break
            results: dict[str, ToolResult] = {}
            ran = self.tools.run(answer.calls, results)
            try:
                async for event in ran:
                    yield event
            finally:
                await ran.aclose()
            tools_run += len(answer.calls)
            done = exchange(answer.calls, results)
            messages += [
                ChatMessage.assistant(answer.text, tool_calls=tuple(answer.calls)),
                *done[1:],
            ]
            self.memory.keep(self.turn.turn_id, done)
        _log.info(
            "talker_replied",
            call_id=self.ctx.call_id,
            turn_id=self.turn.turn_id,
            language=self.language,
            requests=requests,
            tools=tools_run,
            blocked=self.blocked,
        )
        yield ReplyDone()

    def _request(
        self, messages: Sequence[ChatMessage], tools: tuple[ToolSchema, ...]
    ) -> ChatRequest:
        llm = self.settings.llm
        return ChatRequest(
            messages=tuple(messages),
            tools=tools,
            model=llm.model,
            reasoning_effort=llm.reasoning_effort if llm.model in _REASONING else None,
            max_output_tokens=llm.max_output_tokens,
        )

    async def _asked(
        self, request: ChatRequest, answer: _Answer
    ) -> AsyncGenerator[TalkerEvent, None]:
        """The clauses of the model's answer to `request`, as it streams; `answer` gathers the
        rest."""
        started = self.clock.now()
        splitter, unnoted = ClauseStream(max_chars=None), Unnoted()
        stream = self.model.stream(request)
        try:
            async for event in stream:
                if answer.first_token_s is None and isinstance(event, TextDelta | ToolCallRequest):
                    answer.first_token_s = max(0.0, self.clock.now() - started)
                if isinstance(event, TextDelta):
                    answer.text += event.text
                    for said in self._said(splitter.feed(unnoted.feed(event.text))):
                        yield said
                    if self.stopped:
                        return
                elif isinstance(event, ToolCallRequest):
                    if all(event.id != known.id for known in answer.calls):  # each id once
                        answer.calls.append(event)
                elif isinstance(event, Usage):
                    answer.usage = event
        except ProviderError as error:
            _log.warning(
                "talker_model_failed",
                call_id=self.ctx.call_id,
                turn_id=self.turn.turn_id,
                kind=error.kind,
                retryable=error.retryable,
            )
            raise
        finally:
            await _closed(stream)
        for said in self._said((*splitter.feed(unnoted.close()), *splitter.close())):
            yield said

    def _evidence(self) -> Iterable[str]:
        return itertools.chain(self.memory.evidence, self.heard)

    def _said(self, clauses: Iterable[str]) -> list[TalkerEvent]:
        """`clauses`, each spoken once the guard passed it, or blocked (the module's
        docstring)."""
        events: list[TalkerEvent] = []
        for text in clauses:
            if self.stopped:
                break
            guard = self.settings.guard
            verdict = check_ids(text, evidence=self._evidence(), settings=guard, year=self.year)
            if verdict.passed:
                events.append(SpokenClause(text=text, language=self.language))
                continue
            self.blocked += 1
            self.memory.notes[self.turn.turn_id] = BLOCKED
            unsupported = verdict.unsupported
            events.append(ClauseBlocked(text=text, language=self.language, unsupported=unsupported))
            self.stopped = guard.on_block == "drop_rest"
        return events

    def _shown(self, card: Card, tool: str) -> bool:
        """Whether `card`'s text passes the guard; a card that does not is not shown, and is
        logged by its tool's name alone."""
        texts = [card.title, *card.steps, *([card.source] if card.source else [])]
        guard, evidence = self.settings.guard, list(self._evidence())
        if all(
            check_ids(t, evidence=evidence, settings=guard, year=self.year).passed for t in texts
        ):
            return True
        _log.warning("talker_card_blocked", turn_id=self.turn.turn_id, tool=tool)
        return False
