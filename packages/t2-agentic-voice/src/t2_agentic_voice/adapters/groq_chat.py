"""Groq's chat models behind the chat model port (the design's 6.1; D-004; plan 006).

`GroqChat` sends each `ChatRequest` to Groq's chat completions, streamed, and yields its events.
It builds its client as every Groq adapter does (adapters/groq_client.py: the key, base URL and
timeout always passed, the SDK's retries off, every request with the adapter's own headers, a
body that does not open as its JSON does refused unsent, `groq` imported with `GROQ_LOG`
undone), on a connection pool of its own kept open between requests. No public signature names
a `groq` type (the design's 5.3). Public through the `groq` facade (D-021).

- **The request.** The messages (the instructions, the caller's words, the model's own with the
  tool calls it asked for, each tool's result naming its call), the tools as functions, the
  request's `model`, its `max_output_tokens` as Groq's `max_completion_tokens`, its temperature,
  and its `reasoning_effort` only to a model that takes it (core/settings/llm.py's
  `REASONING_MODELS`: Groq refuses the field for the Llama models), and `reasoning_format`
  `hidden` for a model that writes its reasoning into the text otherwise (`HIDDEN_REASONING`,
  D-133); a value the request leaves out is not sent, so Groq's default holds. groq 1.7.0
  builds the body in its parameters' order, the messages first, with no space
  (groq/resources/chat/completions.py; groq/_utils/_json.py), and sends JSON as its `Accept`
  for a streamed request too (the client's `default_headers`): Groq streams because the body
  asks (`"stream":true`), so the request hook sends the SDK's own values.
- **The events**, in order: a `TextDelta` for each piece of the reply's text, never the model's
  reasoning (which gpt-oss streams beside it, in `delta.reasoning`); each tool call whole once
  its choice has finished, its pieces joined by index (the id and the name from the first piece
  that gives them, the argument text from every piece, unparsed: invariant 4 makes parsing the
  tool runner's); the usage the last chunk reports (Groq's `x_groq.usage`, or the chunk's own
  `usage`, its cached tokens from `prompt_tokens_details`); then one `Done` with the finish
  reason (`function_call` read as `tool_calls`).
- **Failures** go through `groq_client.failure` (a 429 with its `retry-after`, a 5xx, a timeout,
  a lost connection, a 4xx `rejected`). A read of the stream that times out or loses its
  connection, which the SDK does not wrap, is `timeout` or `connection_lost`
  (`groq_client.stream_failure`). An error Groq sends
  inside the stream (an SSE `error` event, such as `tool_use_failed` when a Llama model wrote its
  own function text: plan 006's spike) is `rejected`, its code in the details when it is a plain
  name; a stream that ends with no finish reason is a `server_error` (`no_finish`), never a
  silent end.
- **Time.** `llm.timeout_s` bounds the whole request: no wait for Groq, for its answer or for a
  chunk, ends later than that from the request's sending (a `timeout`). The deadline is put on
  each wait, never around a `yield`, so it never cancels the consumer's own work; what has
  already come is still read.
- **Cancellation.** A cancel (or `aclose` between events) closes the response at once: within
  50 ms, leaving no task, and the connection closed with it, since a half-read answer cannot
  carry another request.
- **Connections** stay open between requests for five minutes (`groq_client.LIMITS`), not
  httpx's 5 s (the prototype's D41). `warm()` (the `ConnectionWarmth` port) says whether the
  next request goes out on one of them, from the adapter's own record, never httpx's internals:
  true while less than the keep-alive expiry has passed since a request ended, read to its end
  and closed; false before any, and after a stream that failed or was cancelled, which closes
  its connection. `warm_up()` (the `WarmUp` port) opens one with a GET of Groq's model list,
  which costs nothing. With `reopen_after_cancel` (`warmup.after_cancel`), a cancelled or
  closed stream has a fresh connection opened that way in the background (TD-115), so the next
  request does not pay a new handshake; a failure there is logged by its type alone.
- **Tracing.** The adapter puts nothing on a span, as the speech adapters do not: its usage rides
  on its `Usage` event, and the talker times the first token on the call's clock, for the span
  the session records. No prompt or reply text goes anywhere but the request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from time import monotonic

import httpx
from pydantic import JsonValue, SecretStr

from t2_agentic_voice.adapters.groq_chat_wire import (
    StreamReply,
    UnfinishedError,
    given,
    message_param,
    stream_error_code,
    tool_param,
)
from t2_agentic_voice.adapters.groq_client import (
    DATA_FLOW,
    LIMITS,
    APIConnectionError,
    APIError,
    APIStatusError,
    checked,
    groq_client,
    omit,
    own_headers,
    settings_key,
    stream_failure,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.llm import HIDDEN_REASONING, REASONING_MODELS, LlmSettings
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

log = get_logger(__name__)

# The SDK's chat body opens with its first field, the messages (above).
_OPENS_WITH = b'{"messages":'


class GroqChat:
    """The chat models on Groq; a `ChatModel`, its `ConnectionWarmth` and its `WarmUp`. Each
    request names its own model (`llm.model`), so one adapter serves every arm of a run.
    `transport` replaces the HTTP transport (a test's fake one); by default the adapter talks to
    `base_url` over its own connection pool. Close it with `aclose()`."""

    name: str = "groq"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
        reopen_after_cancel: bool = False,
    ) -> None:
        """The adapter for these values, which it refuses as the settings would (GP-20), each
        error naming the setting and never the value."""
        self._api_key = checked(
            api_key, base_url, ("llm", lambda: LlmSettings(timeout_s=timeout_s))
        )
        self._base_url = base_url
        self._timeout_s = timeout_s
        hook = own_headers(
            self._api_key,
            accept=b"application/json",
            content_type=b"application/json",
            opens_with=_OPENS_WITH,
            refusal="foreign_body",
        )
        self._groq = groq_client(
            api_key=self._api_key,
            base_url=base_url,
            timeout_s=timeout_s,
            hook=hook,
            transport=transport,
        )
        # When a request last ended read to its end, on monotonic(); None: no connection is
        # known to be open.
        self._finished_at: float | None = None
        self._reopen = reopen_after_cancel
        self._reopening: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> GroqChat:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url` and
        `llm.timeout_s`. ConfigurationError naming `T2V_GROQ__API_KEY` (under the settings'
        prefix) when no key is set, as `GroqSTT`'s; `warmup.after_cancel` its
        `reopen_after_cancel`."""
        key = settings_key(settings)
        return cls(
            api_key=key,
            base_url=settings.groq.base_url,
            timeout_s=settings.llm.timeout_s,
            transport=transport,
            reopen_after_cancel=settings.warmup.after_cancel,
        )

    def __repr__(self) -> str:
        return f"GroqChat(base_url={self._base_url!r}, timeout_s={self._timeout_s!r})"

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The model's answer to `request`, as the port's `stream` says (the module's
        docstring). Raises ProviderError on every failure, an answer it cannot read included."""
        deadline = asyncio.get_running_loop().time() + self._timeout_s
        reply = StreamReply()
        ending: list[ChatEvent] = []
        problem: ProviderError | None = None
        try:
            async with asyncio.timeout_at(deadline):
                chunks = await self._groq.chat.completions.create(
                    messages=[message_param(message) for message in request.messages],
                    model=request.model,
                    stream=True,
                    tools=[tool_param(tool) for tool in request.tools] if request.tools else omit,
                    max_completion_tokens=given(request.max_output_tokens),
                    temperature=given(request.temperature),
                    reasoning_effort=given(
                        request.reasoning_effort if request.model in REASONING_MODELS else None
                    ),
                    reasoning_format=given("hidden" if request.model in HIDDEN_REASONING else None),
                )
            async with chunks:  # the response closed however the stream ends
                while True:
                    async with asyncio.timeout_at(deadline):
                        chunk = await anext(chunks, None)
                    if chunk is None:
                        break
                    # Read by the adapter's own models: the SDK's warnings would only repeat them.
                    for event in reply.read(chunk.to_dict(warnings=False)):
                        yield event
            ending = reply.end()
            self._finished_at = monotonic()  # read to its end and closed: kept alive
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            self._finished_at = None  # its connection is not known to be kept
            problem = _failure(error)
        except BaseException:  # a cancel, or a close between events, closed its connection
            self._finished_at = None
            self._reopened()
            raise
        if problem is not None:
            raise problem from None
        for event in ending:
            yield event

    def warm(self) -> bool:
        """Whether the next request goes out on a kept-alive connection (the module's
        docstring)."""
        if self._finished_at is None:
            return False
        expiry = LIMITS.keepalive_expiry
        return expiry is None or monotonic() - self._finished_at < expiry

    async def warm_up(self) -> None:
        """Open a connection with a GET of Groq's model list, which costs nothing (the
        `WarmUp` port), within `timeout_s`. ProviderError on its failure."""
        problem: ProviderError | None = None
        try:
            async with asyncio.timeout(self._timeout_s):
                await self._groq.models.list()
            self._finished_at = monotonic()
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            problem = _failure(error)
        if problem is not None:
            raise problem from None

    async def aclose(self) -> None:
        """Stop a reopen in flight and close the adapter's HTTP connections."""
        self._closed = True
        reopening, self._reopening = self._reopening, None
        if reopening is not None and not reopening.done():
            reopening.cancel()
            await asyncio.gather(reopening, return_exceptions=True)
        await self._groq.close()

    def _reopened(self) -> None:
        """Under `reopen_after_cancel`, open a fresh connection in the background, one at a
        time, unless the adapter is closed."""
        if not self._reopen or self._closed:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # a stream finalized with no loop running: nothing to reopen on
            return
        if self._reopening is None or self._reopening.done():
            self._reopening = asyncio.create_task(self._reopen_now(), name="t2v-chat-reopen")

    async def _reopen_now(self) -> None:
        began = monotonic()
        try:
            await self.warm_up()
        except ProviderError as error:
            log.warning("chat_reopen_failed", error=error.kind)
            return
        log.info("chat_reopened", ms=round((monotonic() - began) * 1000, 1))


def _failure(error: Exception) -> ProviderError:
    """The ProviderError for a failure of a chat request (the module's docstring)."""
    if isinstance(error, UnfinishedError):
        return ProviderError("server_error", False, details={"error": "no_finish"})
    if isinstance(error, APIError) and not isinstance(error, APIStatusError | APIConnectionError):
        details: dict[str, JsonValue] = {"error": "stream_error"}
        if code := stream_error_code(error.body):
            details["code"] = code
        return ProviderError("rejected", False, details=details)
    return stream_failure(error)
