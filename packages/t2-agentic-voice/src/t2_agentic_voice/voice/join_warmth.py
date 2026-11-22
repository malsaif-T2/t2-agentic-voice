"""The warm requests a call sends as it joins (TD-089): one each to its providers, so their
connections are open before its first turn and the first transcript and the first reply do not
pay a TLS handshake (the first turn's transcript took about 733 ms against 490 ms after).

`JoinWarmth.joined` runs once a call, from voice/calls.py's `answer` (never once a turn), and
only under `warmup.at_join` (core/settings/warmup.py: off by default until the warm-up's
measurement keeps it, GP-18). In the background, each its own task, it sends:

- **the speech-to-text** the call hears with (a chosen call's, else the runtime's): its
  `warm_up()` (domain/ports/connection_warmth.py's `WarmUp`: a GET of the provider's model
  list, which costs nothing); a provider without one is sent nothing;
- **the text-to-speech** it speaks with (a chosen call's, else the runtime's): its
  `check_language` for the call's language, the port's own request that sends no synthesis
  (Groq's: a GET of its model list), so it reaches every text-to-speech, the clause cache's
  wrapped one included;
- **the chat model** it writes with (a chosen call's, else the runtime's), for a call with a
  talker, only when its connection is not warm
  (`ConnectionWarmth.warm()`: a model without it counts as cold): its `warm_up()`.

Each request is bounded by `WARM_TIMEOUT_S`; a failure is logged by its type and never fails the
call, which then pays the handshake at its first request, as before. Each is logged as
`call_warmed`: the call, the target, the provider's `name`, the time and the outcome (`warm`,
`failed` with the error's kind or type, or `already_warm`), never an address. `aclose` cancels
what is still in flight.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.connection_warmth import ConnectionWarmth, WarmUp
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech

# The longest a warm request is waited for: past it, the call's first request opens its own.
WARM_TIMEOUT_S = 10.0

Target = Literal["stt", "tts", "chat"]

log = get_logger(__name__)


class JoinWarmth:
    """Each joining call's warm requests (the module's docstring), to `tts` and, when given,
    `chat`, sent only when `on`."""

    def __init__(self, *, on: bool, tts: TextToSpeech, chat: ChatModel | None) -> None:
        self._on, self._tts, self._chat = on, tts, chat
        self._tasks: set[asyncio.Task[None]] = set()

    def joined(
        self,
        call_id: CallId,
        stt: SpeechToText,
        language: str,
        *,
        tts: TextToSpeech | None = None,
        chat: ChatModel | None = None,
    ) -> None:
        """Send the call's warm requests in the background, `stt` the one it hears with, `tts`
        and `chat` the text-to-speech and the chat model it speaks and writes with (a chosen
        call's, else the runtime's: None for the constructor's)."""
        if not self._on:
            return
        if isinstance(stt, WarmUp):
            self._send(call_id, "stt", stt.name, stt.warm_up)
        speaks = self._tts if tts is None else tts
        self._send(call_id, "tts", speaks.name, lambda: speaks.check_language(language))
        chat = self._chat if chat is None else chat
        if chat is None:
            return
        if isinstance(chat, ConnectionWarmth) and chat.warm():
            log.info(
                "call_warmed",
                call_id=call_id,
                target="chat",
                provider=chat.name,
                ms=0.0,
                outcome="already_warm",
            )
        elif isinstance(chat, WarmUp):
            self._send(call_id, "chat", chat.name, chat.warm_up)

    async def aclose(self) -> None:
        """Cancel the warm requests still in flight."""
        tasks, self._tasks = list(self._tasks), set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _send(
        self,
        call_id: CallId,
        target: Target,
        provider: str,
        request: Callable[[], Awaitable[object]],
    ) -> None:
        task = asyncio.create_task(
            _warmed(call_id, target, provider, request), name=f"t2v-warm-{target}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _warmed(
    call_id: CallId, target: Target, provider: str, request: Callable[[], Awaitable[object]]
) -> None:
    """Send one warm request and log its time and outcome; a failure is logged by its type."""
    began = perf_counter()
    failed: str | None = None
    try:
        async with asyncio.timeout(WARM_TIMEOUT_S):
            await request()
    except Exception as error:  # a failed warm request never fails the call
        outcome = "failed"
        failed = error.kind if isinstance(error, ProviderError) else type(error).__name__
    else:
        outcome = "warm"
    ms = round((perf_counter() - began) * 1000, 1)
    log.info(
        "call_warmed",
        call_id=call_id,
        target=target,
        provider=provider,
        ms=ms,
        outcome=outcome,
        error=failed,
    )
