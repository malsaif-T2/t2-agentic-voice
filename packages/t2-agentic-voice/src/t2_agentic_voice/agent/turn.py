"""One reply of the talker's (agent/talker.py's `ChatTalker.reply`; plan 006): from the caller's
turn and the call as it was heard to the events the session plays, within the reply's scope.

- **The request.** The system prompt in the turn's reply language and the register of the
  caller's Arabic over the call (agent/prompt.py, agent/language.py), opened by a line new on
  every request (`llm.vary_first_line`: prompt.py's `FIRST_LINE`), the call as the caller heard
  it with what the talker kept beside it (agent/context.py), then the turn, whole; a request
  after a tool result of the turn ends with a line naming the reply's language (prompt.py's
  `reply_line`). At most `MAX_REQUESTS` a turn: each but the last offers the agent's tools, the
  last none, so the turn ends in words, told so and holding the results with the calls that
  asked for them dropped (agent/context.py's `without_calls`); a tool call the last one makes
  anyway is not run.
- **Speech as it is written.** Each piece the model writes, and each tool call's arguments, are
  filtered first (agent/stray_script.py: no script the agent's languages do not write), so all
  that follows reads one text; a clause the filter left with no letter or digit is none. The
  text goes through the clause splitter as it streams (`ClauseStream`), any note of the
  history's it copied taken out first (agent/context.py's `Unnoted`), and each whole clause,
  once the output guard passed it (agent/speech_guard.py: rule A on claims, for an agent with
  actions, then rule B against the evidence seen this call: its tools' results, the call's
  record, the caller's heard words), is yielded at once. A blocked one is `ClauseBlocked`, with
  its rule's reason, and by `guard.on_block` the rest of the reply goes with it (`drop_rest`:
  no more clause, request or tool) or only it; the next turn's history holds a developer note.
- **Questions.** Before the guard, a clause that asks the caller a question past
  `guard.questions_per_reply` (agent/question_limit.py) is dropped with every clause after it,
  unspoken and unblocked: the reply stops there, but its request's tool calls still run and are
  kept, and no request follows them. `ReplyDone` counts the clauses dropped.
- **Tools** (agent/tool_calls.py). Each call the model asks for starts at once, in the reply's
  scope, and runs through the runner; the first with a progress line gives it, for the
  session to say if the wait runs long (one a reply); each result goes back to the model
  framed as data, a
  result's card is shown once the guard passed its text, and the calls and results are kept
  for the call's next `KEPT_TURNS` turns, which the heard history does not hold.
- **Actions** (the design's 6.4 and 8.2). A request offers the agent's actions beside its tools
  (agent/prompt.py's `tool_definitions`). Rule C: once the model calls an action in a request,
  its text after the call is dropped, unspoken and unblocked, with what the splitter held. The
  call is proposed to the action runner (agent/tool_calls.py): a read-back ends the reply with
  `ReadBackRequested`, after its request's other tools, and no request follows, so nothing the
  model writes is spoken until the turn after the read-back; a refusal goes back to the model
  as a result, and the next request may speak again (to say why, or ask what is missing),
  under rule A. A turn that declined a read-back (`TalkerTurn.declined`) is answered by the
  model in its own words, told so in the turn's message (agent/context.py).
- **Failure and cancel.** A `ProviderError` from the model ends the reply: it is raised from the
  stream after any clause already given, for the session to say the `error` notice (which it
  says too for a reply that ends with no clause); a request cut at `max_output_tokens`
  (`length`) is logged by its model, its words so far given as written; any other
  error comes out as it is (a fake's `ScriptExhaustedError`, an AssertionError, fails its test).
  A cancel of the reply's scope cancels the task that iterates the stream, so the model's
  request and every tool of the scope stop at once, and no `ReplyDone` comes. The model's stream
  is closed as the reply leaves it, whatever ends it (domain/ports/chat_model.py's `closing`).
- **Time** is the call's clock's alone: a tool's `ms`, a request's
  `first_token_s` and the prompt's date (the runner times each tool's timeout on it too).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable, Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.agent.context import (
    BLOCKED,
    CLAIM_BLOCKED,
    Unnoted,
    call_context,
    continued,
    declined_note,
    history,
    turn_message,
    without_calls,
)
from t2_agentic_voice.agent.events import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ReadBackRequested,
    ReplyDone,
    ReplyScope,
    SpokenClause,
    TalkerEvent,
)
from t2_agentic_voice.agent.language import call_register, reply_language
from t2_agentic_voice.agent.leaked_reasoning import LeakedReasoning
from t2_agentic_voice.agent.prompt import (
    compose_prompt,
    reply_line,
    tool_definitions,
    with_first_line,
)
from t2_agentic_voice.agent.question_limit import QuestionLimit
from t2_agentic_voice.agent.speech_guard import SpeechGuard
from t2_agentic_voice.agent.stray_script import StrayScript
from t2_agentic_voice.agent.tool_calls import Memory, ToolCalls, exchange
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.llm import REASONING_MODELS
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
    closing,
)
from t2_agentic_voice.domain.text.clauses import ClauseStream

_log = get_logger(__name__)
# The most model requests one turn makes; the last offers no tool, so the turn ends in words.
MAX_REQUESTS = 3


@dataclass
class _Answer:
    """What one model request gave: its text, its tool calls, its usage, its first token's
    time."""

    text: str = ""
    calls: list[ToolCallRequest] = field(default_factory=list)
    usage: Usage | None = None
    first_token_s: float | None = None


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
        actions: ActionRunner | None = None,
        record: ActionRecord | None = None,
    ) -> None:
        self.agent, self.model, self.runner = agent, model, runner
        self.settings, self.clock, self.memory = settings, clock, memory
        self.turn, self.scope, self.actions = turn, scope, actions
        spoken = [language.tag for language in agent.languages]
        self.language = reply_language(turn, call=call_language, spoken=spoken)
        self.ctx = call_context(
            caller=caller, call_id=call_id, language=self.language, actions=actions, record=record
        )
        heard = [t.words for t in turn.conversation.turns if t.fate != "dropped" and t.words]
        self.heard = (*heard, turn.words)
        self.register = call_register(self.heard)  # the call's so far, this turn's among it
        self.stopped = False  # a blocked clause dropped the rest of the reply
        self.blocked = 0
        self.guard = SpeechGuard(
            settings=settings.guard,
            year=clock.wall().year,
            actions=() if actions is None else actions.actions,
            record=record,
            memory=memory,
            heard=self.heard,
        )
        self.scripts = StrayScript.of(agent, settings)
        self.questions = QuestionLimit(settings.guard.questions_per_reply)
        self.leak = LeakedReasoning(arabic=self.language != "en")  # D-089
        self.tools = ToolCalls(
            runner=runner,
            ctx=self.ctx,
            clock=clock,
            scope=scope,
            memory=memory,
            turn_id=turn.turn_id,
            shown=self._shown,
            actions=actions,
            register=self.register,
        )

    async def events(self) -> AsyncGenerator[TalkerEvent, None]:
        """The reply's events, in order, ending with `ReplyDone` unless cancelled."""
        named = frozenset(r for r in (self.turn.over_reply, self.turn.cut_reply) if r is not None)
        today, register = self.clock.wall().date(), self.register
        prompt = compose_prompt(self.agent, language=self.language, today=today, register=register)
        past = history(
            self.turn.conversation,
            exchanges=self.memory.exchanges,
            notes=self.memory.notes,
            named=named,
            continued=continued(self.turn),  # the turns it goes on with, said in its message
        )
        messages = [ChatMessage.system(prompt), *past, turn_message(self.turn)]
        if self.turn.declined is not None:  # kept beside the turn, once, for the turns after it
            note = ChatMessage.system(declined_note(self.turn.declined))
            if note not in self.memory.exchanges.get(self.turn.turn_id, ()):
                self.memory.keep(self.turn.turn_id, [note])
        requests = tools_run = 0
        for index in range(MAX_REQUESTS):
            last = index == MAX_REQUESTS - 1
            tools = () if last else tool_definitions(self.runner, self.actions)
            request = self._request(messages, tools, after_tools=tools_run > 0)
            requests += 1
            yield ModelRequested(model=request.model)
            answer = _Answer()
            asked = self._asked(request, answer)
            try:
                async for event in asked:
                    yield event
            finally:
                await asked.aclose()
            stray, scripts = self.scripts.take()
            yield ModelReplied(
                model=request.model,
                usage=answer.usage,
                first_token_s=answer.first_token_s,
                stray_characters=stray,
                stray_scripts=scripts,
            )
            if self.stopped or self.leak.found or not answer.calls:
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
            if self.tools.plan is not None:  # read back: nothing more of the model this turn
                yield ReadBackRequested(plan=self.tools.plan)
                break
            if self.questions.stopped:  # nothing more of the reply is said: no more request
                break
        self.questions.logged(call_id=self.ctx.call_id, turn_id=self.turn.turn_id)
        self.leak.logged(call_id=self.ctx.call_id, turn_id=self.turn.turn_id)
        _log.info(
            "talker_replied",
            call_id=self.ctx.call_id,
            turn_id=self.turn.turn_id,
            language=self.language,
            requests=requests,
            tools=tools_run,
            blocked=self.blocked,
            read_back=self.tools.plan is not None,
        )
        yield ReplyDone(unsaid_clauses=self.questions.unsaid)

    def _request(
        self, messages: Sequence[ChatMessage], tools: tuple[ToolSchema, ...], *, after_tools: bool
    ) -> ChatRequest:
        llm = self.settings.llm
        if llm.vary_first_line:  # so no two requests share a cached prefix (the setting's text)
            messages = [ChatMessage.system(with_first_line(messages[0].content)), *messages[1:]]
        if not tools:
            messages = without_calls(messages)
        if after_tools:  # the request's own line, never kept in the turn's messages
            line = reply_line(self.language, self.register, last=not tools)
            messages = [*messages, ChatMessage.system(line)]
        return ChatRequest(
            messages=tuple(messages),
            tools=tools,
            model=llm.model,
            reasoning_effort=llm.reasoning_effort if llm.model in REASONING_MODELS else None,
            max_output_tokens=llm.max_output_tokens,
        )

    async def _asked(
        self, request: ChatRequest, answer: _Answer
    ) -> AsyncGenerator[TalkerEvent, None]:
        """The clauses of the model's answer to `request`, as it streams; `answer` gathers the
        rest."""
        started = self.clock.now()
        whole_sentences = self.language == "en"  # D-077
        splitter = ClauseStream(max_chars=None, whole_sentences=whole_sentences)
        unnoted = Unnoted()
        acted = False  # rule C: an action was called, and what the model writes after is dropped
        dropped = False  # whether it wrote any
        try:
            async with closing(self.model.stream(request)) as stream:
                async for event in stream:
                    if answer.first_token_s is None and isinstance(
                        event, TextDelta | ToolCallRequest
                    ):
                        answer.first_token_s = max(0.0, self.clock.now() - started)
                    if isinstance(event, TextDelta) and not acted:
                        piece = self.leak.text(self.scripts.text(event.text))
                        answer.text += piece
                        for said in self._said(splitter.feed(unnoted.feed(piece))):
                            yield said
                        if self.stopped:
                            return
                        if self.leak.found:  # the rest is reasoning: what was held is said
                            break
                    elif isinstance(event, TextDelta):
                        dropped = dropped or bool(event.text.strip())
                    elif isinstance(event, ToolCallRequest):
                        if all(event.id != known.id for known in answer.calls):  # each id once
                            answer.calls.append(self.scripts.call(event))
                        acted = acted or self.tools.is_action(event.name)
                    elif isinstance(event, Usage):
                        answer.usage = event
                    elif isinstance(event, Done) and event.finish_reason == "length":
                        _log.warning(
                            "talker_reply_truncated",
                            call_id=self.ctx.call_id,
                            turn_id=self.turn.turn_id,
                            model=request.model,
                            finish_reason=event.finish_reason,
                        )
        except ProviderError as error:
            _log.warning(
                "talker_model_failed",
                call_id=self.ctx.call_id,
                turn_id=self.turn.turn_id,
                kind=error.kind,
                retryable=error.retryable,
            )
            raise
        if acted:  # rule C: what the splitter held goes too, unspoken
            held = [*splitter.feed(unnoted.feed(self.leak.close()) + unnoted.close())]
            held += splitter.close()
            if dropped or any(text.strip() for text in held):
                _log.info("talker_text_after_action_dropped", turn_id=self.turn.turn_id)
            return
        rest = unnoted.feed(self.leak.close()) + unnoted.close()
        for said in self._said((*splitter.feed(rest), *splitter.close())):
            yield said

    def _said(self, clauses: Iterable[str]) -> list[TalkerEvent]:
        """`clauses`, each spoken once the guard passed it, or blocked, or dropped past the
        reply's question limit (the module's docstring)."""
        events: list[TalkerEvent] = []
        for text in clauses:
            if self.stopped:
                break
            if self.scripts.changed and not any(char.isalnum() for char in text):
                continue  # the filter left it nothing to say: never a clause said as silence
            if self.questions.drops(text, said=self.guard.passed):
                continue  # a question past the reply's limit, or a clause after one: unsaid
            checked = self.guard.check(text)
            if checked.passed:
                events.append(SpokenClause(text=text, language=self.language))
                continue
            self.blocked += 1
            claim = checked.reason == "unsupported_claim"
            self.memory.notes[self.turn.turn_id] = CLAIM_BLOCKED if claim else BLOCKED
            events.append(
                ClauseBlocked(
                    text=text,
                    language=self.language,
                    unsupported=checked.unsupported,
                    reason=checked.reason,
                )
            )
            self.stopped = self.settings.guard.on_block == "drop_rest"
        return events

    def _shown(self, card: Card, tool: str) -> bool:
        """Whether `card`'s text passes the guard; a card that does not is not shown, and is
        logged by its tool's name alone."""
        if self.guard.ids_pass(card.texts()):
            return True
        _log.warning("talker_card_blocked", turn_id=self.turn.turn_id, tool=tool)
        return False
