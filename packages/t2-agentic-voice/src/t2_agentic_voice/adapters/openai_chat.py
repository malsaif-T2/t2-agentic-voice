"""OpenAI's chat models behind the chat model port (D-112): `OpenAIChat` sends each
`ChatRequest` to OpenAI's own Chat Completions, streamed, and yields its events. It talks raw
HTTPS through httpx with no SDK, as every provider measured beside Groq does
(adapters/provider_http.py, D-100): its own client, no redirect followed, no proxy or CA
variable read, so nothing reads a variable of its own. `llm.provider = "openai"` picks it, inside
a `ChatRoute` that keeps the library's own checks on Groq (api/providers.py's `chat_model`).

- **The request**, as Groq's adapter sends it and built by the same wire
  (adapters/groq_chat_wire.py's `message_param` and `tool_param`, since Groq's API copies
  OpenAI's): the messages, the tools as functions with `parallel_tool_calls` (the talker runs
  every call at once and refuses a second action itself: agent/tool_calls.py), the model,
  `max_output_tokens` as `max_completion_tokens`, the temperature, `reasoning_effort` only to a
  model that takes it (core/settings/llm.py's `REASONING_MODELS`, where the settings hold
  OpenAI's models to `none`, the one effort its Chat Completions take with tools), and
  `stream_options.include_usage`, so the stream's last chunk carries the usage. A value the
  request leaves out is not sent, so OpenAI's default holds.
- **The events**, read by Groq's `StreamReply`: a `TextDelta` for each piece of text, each tool
  call whole once its choice has finished, the usage (its cached tokens from
  `prompt_tokens_details`), then one `Done`. Every line of the stream is read to its end, so
  the connection is kept.
- **Failures**: `provider_http.http_failure` (a 429 with its `retry-after`; 408, 409 and 5xx
  retryable; any other refusal `rejected`; a timeout; a lost connection), its details naming
  OpenAI and the failure's class, never the answer's body, which may echo the request. An
  `error` OpenAI sends inside the stream is `rejected`, its code kept when a plain name; a chunk
  that is not JSON of a chunk's shape is a `server_error`, and a stream that ends with no
  finish reason one too (`no_finish`), never a silent end.
- **Time, cancellation and connections**, as Groq's adapter (adapters/groq_chat.py's
  docstring): `llm.timeout_s` bounds the whole request, its deadline on each wait and never
  around a `yield`; a cancel closes the response at once; connections stay open five minutes;
  `warm()` comes from the adapter's own record, `warm_up()` is a GET of the model list, which
  costs nothing, and `reopen_after_cancel` opens a fresh connection after a cancel.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from time import monotonic

import httpx
from pydantic import SecretStr

from t2_agentic_voice.adapters.groq_chat_wire import StreamReply
from t2_agentic_voice.adapters.groq_client import LIMITS
from t2_agentic_voice.adapters.openai_chat_wire import (
    DATA_FLOW,
    body_of,
    checked,
    chunk_of,
    failure,
    no_key,
)
from t2_agentic_voice.adapters.provider_http import http_client, ok_status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

log = get_logger(__name__)


class OpenAIChat:
    """The chat models on OpenAI's API; a `ChatModel`, its `ConnectionWarmth` and its `WarmUp`.
    Each request names its own model, so one adapter serves every arm of a run. `transport`
    replaces the HTTP transport (a test's fake one). Close it with `aclose()`."""

    name: str = "openai"
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
        self._api_key = checked(api_key, base_url)
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._http = http_client(timeout_s=timeout_s, transport=transport)
        self._finished_at: float | None = None  # when a request last ended read to its end
        self._reopen = reopen_after_cancel
        self._reopening: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> OpenAIChat:
        """The adapter the settings describe: the `openai` group's key and base URL,
        `llm.timeout_s`, and `warmup.after_cancel` its `reopen_after_cancel`; a
        ConfigurationError naming `T2V_OPENAI__API_KEY` (under the settings' prefix) when no
        key is set."""
        key = settings.openai.resolved_api_key(settings.prefix)
        if key is None:
            raise no_key(settings.env_name("openai", "api_key"))
        return cls(
            api_key=key,
            base_url=settings.openai.base_url,
            timeout_s=settings.llm.timeout_s,
            transport=transport,
            reopen_after_cancel=settings.warmup.after_cancel,
        )

    def __repr__(self) -> str:
        return f"OpenAIChat(base_url={self._base_url!r}, timeout_s={self._timeout_s!r})"

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The model's answer to `request`, as the port's `stream` says (the module's
        docstring). Raises ProviderError on every failure, an answer it cannot read included."""
        deadline = asyncio.get_running_loop().time() + self._timeout_s
        reply = StreamReply()
        ending: list[ChatEvent] = []
        problem: ProviderError | None = None
        try:
            async with asyncio.timeout_at(deadline):
                response = await self._http.send(self._post(request), stream=True)
            try:
                ok_status(response)
                lines = response.aiter_lines()
                while True:
                    async with asyncio.timeout_at(deadline):
                        line = await anext(lines, None)
                    if line is None:
                        break
                    chunk = chunk_of(line)
                    if chunk is None:
                        continue
                    for event in reply.read(chunk):
                        yield event
            finally:
                await response.aclose()
            ending = reply.end()
            self._finished_at = monotonic()  # read to its end and closed: kept alive
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            self._finished_at = None
            problem = failure(error)
        except BaseException:  # a cancel, or a close between events, closed its connection
            self._finished_at = None
            self._reopened()
            raise
        if problem is not None:
            raise problem from None
        for event in ending:
            yield event

    def warm(self) -> bool:
        """Whether the next request goes out on a kept-alive connection."""
        if self._finished_at is None:
            return False
        expiry = LIMITS.keepalive_expiry
        return expiry is None or monotonic() - self._finished_at < expiry

    async def warm_up(self) -> None:
        """Open a connection with a GET of OpenAI's model list, which costs nothing (the
        `WarmUp` port), within `timeout_s`. ProviderError on its failure."""
        problem: ProviderError | None = None
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._http.get(f"{self._base_url}/models", headers=self._head())
            ok_status(response)
            self._finished_at = monotonic()
        except Exception as error:  # every failure; never a cancel
            problem = failure(error)
        if problem is not None:
            raise problem from None

    async def aclose(self) -> None:
        """Stop a reopen in flight and close the adapter's HTTP connections."""
        self._closed = True
        reopening, self._reopening = self._reopening, None
        if reopening is not None and not reopening.done():
            reopening.cancel()
            await asyncio.gather(reopening, return_exceptions=True)
        await self._http.aclose()

    def _head(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def _post(self, request: ChatRequest) -> httpx.Request:
        """The streamed request for `request` (the module's docstring)."""
        headers = self._head() | {"Accept": "text/event-stream"}
        url = f"{self._base_url}/chat/completions"
        return self._http.build_request("POST", url, json=body_of(request), headers=headers)

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
