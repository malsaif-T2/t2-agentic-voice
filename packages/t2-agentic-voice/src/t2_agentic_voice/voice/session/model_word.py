"""The session's own chat request, timed, for overlap_ask.py and yes_ask.py, each of which keeps
its own rules (when it asks, what it asks, how it reads the answer, what it logs).

The request is a call's chat request, made only with the call's chat model
(`CallSetup.overlap_model`) and counted in its usage as the talker's are (usage.py), its tokens
counted however it ends. It runs as a task of the asker's cancel scope (scope.py), within its
timeout on the call's clock: the model's whole answer, its text deltas joined, as the asker
reads it; `failed` for its failure, logged by its kind alone under the asker's line, never the
words; `timeout` once the timeout passed first, the request then cancelled.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import ChatRequest, TextDelta, Usage
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.usage import Usage as CallUsage

_log = get_logger(__name__)
# A request that gave no answer: it failed, or ran out of time.
NoWord = Literal["failed", "timeout"]


async def model_word[T](
    setup: CallSetup,
    usage: CallUsage,
    request: ChatRequest,
    read_as: Callable[[str], T],
    *,
    scope: CancelScope,
    timeout_s: float,
    name: str,
    turn_id: TurnId,
    failed_line: str,
) -> T | NoWord:
    """The call's chat model's whole answer to `request`, asked for the caller's turn
    `turn_id`, within `timeout_s` on the call's clock, in `scope` (the module's docstring), read
    by `read_as`: its tasks named `<name>-read-<turn>` and `<name>-timer-<turn>`, a failure
    logged as `failed_line`."""
    answer = _answer(setup, usage, request, failed_line)
    read = scope.start(answer, name=f"{name}-read-{turn_id}")
    timer = scope.start(setup.clock.sleep(timeout_s), name=f"{name}-timer-{turn_id}")
    await asyncio.wait((read, timer), return_when=asyncio.FIRST_COMPLETED)
    timer.cancel()
    if not read.done():
        read.cancel()
        return "timeout"
    text = read.result()
    return "failed" if text is None else read_as(text)


async def _answer(
    setup: CallSetup, usage: CallUsage, request: ChatRequest, failed_line: str
) -> str | None:
    """The model's whole answer; None for its failure, logged by kind. Never raises (the scope
    would log its own line) but for a cancel."""
    model = setup.overlap_model
    if model is None:  # never so: each asker asks only with a model
        return None
    usage.chat_requested(request.model)
    replied: Usage | None = None
    parts: list[str] = []
    try:
        async for event in model.stream(request):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, Usage):
                replied = event
    except Exception as error:
        failure = error.kind if isinstance(error, ProviderError) else type(error).__qualname__
        _log.warning(failed_line, call_id=setup.call_id, failure=failure)
        return None
    finally:
        usage.chat_replied(request.model, replied)
    return "".join(parts)
