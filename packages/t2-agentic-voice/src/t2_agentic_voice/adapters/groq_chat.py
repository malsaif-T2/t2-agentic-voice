"""Groq's chat models behind the chat model port (the design's 6.1; D-004; plan 006).

`GroqChat` sends each `ChatRequest` to Groq's chat completions with the request's own model,
reasoning effort, output cap and temperature, streamed, and yields its events: the text as it
comes, each tool call whole once its arguments' text has come (unparsed: the tool runner parses
them), the usage, and one `Done`. It builds its client as every Groq adapter does
(adapters/groq_client.py: the key, base URL and timeout always passed, the SDK's retries off,
every request with the adapter's own headers, a body that does not open as its JSON does refused
unsent, every failure a `ProviderError` with its kind, `retryable` and `retry_after_s`, `groq`
imported with `GROQ_LOG` undone), on one connection pool kept open between requests, as plan
006 asks. A cancel stops it within 50 ms, leaving no task or connection. No public
signature names a `groq` type (the design's 5.3). Public through the `groq` facade (D-021).

What `stream` does is plan 006's Track A (with its tests on a fake transport); this module holds
the adapter's shell: its constructor, `name`, `data_flow`, `from_settings` and `aclose`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from pydantic import SecretStr

from t2_agentic_voice.adapters.groq_client import (
    DATA_FLOW,
    checked,
    groq_client,
    no_key,
    own_headers,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

# The SDK's chat body opens with its first field, the messages (groq/resources/chat/
# completions.py builds the body in its parameters' order).
_OPENS_WITH = b'{"messages":'


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

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The model's answer to `request`, as the port's `stream` says (the module's
        docstring)."""
        raise NotImplementedError("the Groq chat adapter's stream is plan 006's Track A")

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._groq.close()
