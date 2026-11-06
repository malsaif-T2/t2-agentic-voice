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
  and its `reasoning_effort` only to a model that takes it (`REASONING_MODELS`: Groq refuses the
  field for the Llama models); a value the request leaves out is not sent, so Groq's default
  holds. groq 1.7.0 builds the body in its parameters' order, the messages first, with no space
  (groq/resources/chat/completions.py; groq/_utils/_json.py), and sends JSON as its `Accept` for
  a streamed request too (the client's `default_headers`): Groq streams because the body asks
  (`"stream":true`), so the request hook sends the SDK's own values.
- **The events**, in order: a `TextDelta` for each piece of the reply's text, never the model's
  reasoning (which gpt-oss streams beside it, in `delta.reasoning`); each tool call whole once
  its choice has finished, its pieces joined by index (the id and the name from the first piece
  that gives them, the argument text from every piece, unparsed: invariant 4 makes parsing the
  tool runner's); the usage the last chunk reports (Groq's `x_groq.usage`, or the chunk's own
  `usage`, its cached tokens from `prompt_tokens_details`); then one `Done` with the finish
  reason (`function_call` read as `tool_calls`).
- **Failures** go through `groq_client.failure` (a 429 with its `retry-after`, a 5xx, a timeout,
  a lost connection, a 4xx `rejected`). A read of the stream that times out or loses its
  connection, which the SDK does not wrap, is `timeout` or `connection_lost`. An error Groq sends
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
  httpx's 5 s (the prototype's D41).
- **Tracing.** The adapter puts nothing on a span, as the speech adapters do not: its usage rides
  on its `Usage` event, and the talker times the first token on the call's clock, for the span
  the session records. No prompt or reply text goes anywhere but the request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

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
    APIConnectionError,
    APIError,
    APIStatusError,
    checked,
    failure,
    groq_client,
    no_key,
    omit,
    own_headers,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

# The SDK's chat body opens with its first field, the messages (above).
_OPENS_WITH = b'{"messages":'
# The models that take `reasoning_effort` (groq 1.7.0's reference for the field: "openai/gpt-oss-
# 20b and openai/gpt-oss-120b support 'low', 'medium', or 'high'"); Groq refuses it for the
# others the settings name, the Llama models of runs K and U (plan 006).
REASONING_MODELS = frozenset({"openai/gpt-oss-120b", "openai/gpt-oss-20b"})


class GroqChat:
    """The chat models on Groq; a `ChatModel`. Each request names its own model
    (`llm.model`), so one adapter serves every arm of a run. `transport` replaces the HTTP
    transport (a test's fake one); by default the adapter talks to `base_url` over its own
    connection pool. Close it with `aclose()`."""

    name: str = "groq"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
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

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> GroqChat:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url` and
        `llm.timeout_s`. ConfigurationError naming `T2V_GROQ__API_KEY` (under the settings'
        prefix) when no key is set, as `GroqSTT`'s."""
        key = settings.groq.resolved_api_key(settings.prefix)
        if key is None:
            raise no_key(
                settings.env_name("groq", "api_key"),
                settings.env_name("groq", "api_key_file"),
                settings.saw("GROQ_API_KEY"),
            )
        return cls(
            api_key=key,
            base_url=settings.groq.base_url,
            timeout_s=settings.llm.timeout_s,
            transport=transport,
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
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            problem = _failure(error)
        if problem is not None:
            raise problem from None
        for event in ending:
            yield event

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._groq.close()


def _failure(error: Exception) -> ProviderError:
    """The ProviderError for a failure of a chat request (the module's docstring)."""
    if isinstance(error, UnfinishedError):
        return ProviderError("server_error", False, details={"error": "no_finish"})
    if isinstance(error, httpx.TimeoutException):
        return ProviderError("timeout", True, details={"error": type(error).__name__})
    if isinstance(error, httpx.TransportError):
        return ProviderError("connection_lost", True, details={"error": type(error).__name__})
    if isinstance(error, APIError) and not isinstance(error, APIStatusError | APIConnectionError):
        details: dict[str, JsonValue] = {"error": "stream_error"}
        if code := stream_error_code(error.body):
            details["code"] = code
        return ProviderError("rejected", False, details=details)
    return failure(error)
