"""What one model request of a turn gives (agent/turn.py's `Turn`, whose docstring holds the
rules): its clauses as the answer streams (`answer_events`), each piece through the stray-script
filter, the dot runs under `guard.plain_speech` (agent/plain_speech.py), the leak check, the
clause splitter and the output guard, an action's text after its
call dropped (rule C), a cut at `max_output_tokens` and a model's failure logged; and the rest
of the answer (`Answer`): its text, its tool calls, its usage, its first token's time, and
whether the request went out on a kept-alive connection (`warm`, read from the model just before
it went: domain/ports/connection_warmth.py's `warm_now`, None when the model does not say).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from t2_agentic_voice.agent.context import Unnoted
from t2_agentic_voice.agent.events import TalkerEvent
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
                    if reply.gate.stopped or reply.gate.not_speech:
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
