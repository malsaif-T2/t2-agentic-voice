"""What one model request of a turn gives (agent/turn.py's `Turn`, whose docstring holds the
rules): the request from its `ModelRequested` to its `ModelReplied` (`requested`); its clauses as
the answer streams (`answer_events`), each piece through the stray-script filter, the dot runs
under `guard.plain_speech` (agent/plain_speech.py), the leak check, the clause splitter and the
output guard, an action's text after its call dropped (rule C), a cut at `max_output_tokens`
and a model's failure logged; and the rest of the answer (`Answer`): its text, its tool calls,
its usage, its first token's time, and whether the request went out on a kept-alive connection
(`warm`, read from the model just before it went: domain/ports/connection_warmth.py's
`warm_now`, None when the model does not say).

**A rejected request sent once more** (`llm.retry_rejected`, off by default, D-132; the owner's
call of 2026-11-19, where Groq refused a request whose tool call the model wrote malformed,
`tool_use_failed`, and the caller heard the error notice): a request the provider rejects
(`ProviderError` of kind `rejected`) before any clause of it was given, while neither a leak nor
the question limit stopped the reply, is built again (a new first line, under
`llm.vary_first_line`) and sent once more, nothing of the first kept (its text, its tool calls,
what the leak check held); logged as `talker_request_sent_again`. A second rejection of the
same request, a rejection after a clause, or any other failure ends the reply as before.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from t2_agentic_voice.agent.context import Unnoted
from t2_agentic_voice.agent.events import ModelReplied, ModelRequested, TalkerEvent
from t2_agentic_voice.agent.plain_speech import DotRuns
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import (
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    Usage,
    closing,
)
from t2_agentic_voice.domain.ports.connection_warmth import warm_now
from t2_agentic_voice.domain.text.clauses import ClauseStream

if TYPE_CHECKING:
    from t2_agentic_voice.agent.turn import Turn

_log = get_logger(__name__)


@dataclass
class Answer:
    """What one model request gave: its text, its tool calls, its usage, its first token's
    time, and whether it went out on a kept-alive connection (`warm`)."""

    text: str = ""
    calls: list[ToolCallRequest] = field(default_factory=list)
    usage: Usage | None = None
    first_token_s: float | None = None
    warm: bool | None = None

    def clear(self) -> None:
        """Nothing gathered: its request is sent once more (the module's docstring)."""
        self.text, self.calls, self.usage = "", [], None
        self.first_token_s = self.warm = None

    def replied(self, model: str, stray: int, scripts: tuple[str, ...]) -> ModelReplied:
        """The request to `model` ended: its usage, first token's time and warmth, and how many
        characters of it the stray-script filter took out (`stray`), of which `scripts`."""
        return ModelReplied(
            model=model,
            usage=self.usage,
            first_token_s=self.first_token_s,
            warm_connection=self.warm,
            stray_characters=stray,
            stray_scripts=scripts,
        )


async def requested(
    reply: Turn, build: Callable[[], ChatRequest], answer: Answer
) -> AsyncGenerator[TalkerEvent, None]:
    """One request of the turn `reply`, built by `build`: its `ModelRequested`, its clauses as
    they stream and its `ModelReplied`, sent once more when the provider rejects it first (the
    module's docstring); `answer` gathers the rest."""
    again = reply.settings.llm.retry_rejected
    while True:
        request = build()
        yield ModelRequested(model=request.model)
        reply.gate.begin()
        asked = answer_events(reply, request, answer)
        given = False  # a clause of it was given: said, or blocked with the notice
        try:
            async for event in asked:
                given = True
                yield event
        except ProviderError as error:
            stopped = reply.leak.found or reply.gate.questions.stopped
            if not again or given or stopped or error.kind != "rejected":
                raise
            again = False  # never twice for one request
            reply.leak.close()  # what it held of the first is never said
            reply.scripts.take()
            answer.clear()
            ids = {"call_id": reply.ctx.call_id, "turn_id": reply.turn.turn_id}
            _log.info("talker_request_sent_again", **ids, kind=error.kind)
            continue
        finally:
            await asked.aclose()
        yield answer.replied(request.model, *reply.scripts.take())
        return


async def answer_events(
    reply: Turn, request: ChatRequest, answer: Answer
) -> AsyncGenerator[TalkerEvent, None]:
    """The clauses of the model's answer to `request` in the turn `reply`, as it streams;
    `answer` gathers the rest."""
    answer.warm = warm_now(reply.model)
    started = reply.clock.now()
    whole_sentences = reply.language == "en"  # D-077
    splitter = ClauseStream(max_chars=None, whole_sentences=whole_sentences)
    unnoted, dots = Unnoted(), DotRuns(on=reply.settings.guard.plain_speech)  # D-111
    acted = False  # rule C: an action was called, and what the model writes after is dropped
    dropped = False  # whether it wrote any
    try:
        async with closing(reply.model.stream(request)) as stream:
            async for event in stream:
                if answer.first_token_s is None and isinstance(event, TextDelta | ToolCallRequest):
                    answer.first_token_s = max(0.0, reply.clock.now() - started)
                if isinstance(event, TextDelta) and not acted:
                    piece = reply.leak.text(dots.feed(reply.scripts.text(event.text)))
                    answer.text += piece
                    for said in reply.gate.said(splitter.feed(unnoted.feed(piece))):
                        yield said
                    if reply.gate.stopped or reply.gate.ended:  # D-111, a clause held back
                        reply.leak.close()  # what the leak check held of it is never said
                        return
                    if reply.leak.found:  # the rest is reasoning: what was held is said
                        break
                elif isinstance(event, TextDelta):
                    dropped = dropped or bool(event.text.strip())
                elif isinstance(event, ToolCallRequest):
                    if all(event.id != known.id for known in answer.calls):  # each id once
                        answer.calls.append(reply.scripts.call(event))
                    acted = acted or reply.tools.is_action(event.name)
                elif isinstance(event, Usage):
                    answer.usage = event
                elif isinstance(event, Done) and event.finish_reason == "length":
                    _log.warning(
                        "talker_reply_truncated",
                        call_id=reply.ctx.call_id,
                        turn_id=reply.turn.turn_id,
                        model=request.model,
                        finish_reason=event.finish_reason,
                    )
    except ProviderError as error:
        _log.warning(
            "talker_model_failed",
            call_id=reply.ctx.call_id,
            turn_id=reply.turn.turn_id,
            kind=error.kind,
            retryable=error.retryable,
        )
        raise
    tail = reply.leak.text(dots.close())
    if acted:  # rule C: what the splitter held goes too, unspoken
        held = [*splitter.feed(unnoted.feed(tail + reply.leak.close()) + unnoted.close())]
        held += splitter.close()
        if dropped or any(text.strip() for text in held):
            _log.info("talker_text_after_action_dropped", turn_id=reply.turn.turn_id)
        return
    rest = unnoted.feed(tail + reply.leak.close()) + unnoted.close()
    for said in reply.gate.said((*splitter.feed(rest), *splitter.close())):
        yield said
