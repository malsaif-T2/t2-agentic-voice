"""The fake chat models (the design's 9.1; plan 006), for a team's tests and the library's: each
a `ChatModel` (domain/ports/chat_model.py) that sends nothing anywhere and keeps every request it
was given (`requests`), so a test reads what the talker asked.

- **`ScriptedLLM`**: a script with one entry per model request, each the events that request
  streams. A caller's turn that uses a read tool makes two requests: one that calls the tool,
  one that answers from its result. When the script runs out, the next request fails clearly,
  with the requests so far and the last user text, so a test that asked once too often says
  where. `reply(text)` and `call_tool(name, **arguments)` build an entry's events.
- **`FunctionLLM(fn)`**: a custom fake, `fn` taking each request and giving its events, so a
  test need not count requests (one that answers by the last user text, or by a tool result).

Each honours the port's rules: a cancel stops its stream at once, and a stream ends with one
`Done`. Plan 006's Track A builds them; this module holds their shapes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Sequence

from pydantic import JsonValue

from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

# Where a fake sends what it is given: nowhere.
FAKE_DATA_FLOW = DataFlow(
    provider="none (a fake in the test's process)",
    processed_in="the test's process",
    stored_in="nowhere",
    retention="none",
)


class ScriptedLLM:
    """A chat model that plays `script`, one entry per request, in order (the module's
    docstring); a `ChatModel`."""

    name: str = "scripted"
    data_flow: DataFlow = FAKE_DATA_FLOW

    def __init__(self, script: Sequence[Sequence[ChatEvent]]) -> None:
        self.script = tuple(tuple(entry) for entry in script)
        self.requests: list[ChatRequest] = []

    @staticmethod
    def reply(text: str) -> tuple[ChatEvent, ...]:
        """An entry that answers with `text`, then ends (`Done` of `stop`)."""
        raise NotImplementedError("ScriptedLLM is plan 006's Track A")

    @staticmethod
    def call_tool(name: str, **arguments: JsonValue) -> tuple[ChatEvent, ...]:
        """An entry that calls the tool `name` with `arguments`, written as the model writes
        them (JSON text), then ends (`Done` of `tool_calls`)."""
        raise NotImplementedError("ScriptedLLM is plan 006's Track A")

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The next entry's events, `request` kept; fails clearly when the script has run out."""
        raise NotImplementedError("ScriptedLLM is plan 006's Track A")

    async def aclose(self) -> None:
        """Nothing to close."""


class FunctionLLM:
    """A chat model whose every request `fn` answers with the events it gives; a
    `ChatModel`."""

    name: str = "function"
    data_flow: DataFlow = FAKE_DATA_FLOW

    def __init__(self, fn: Callable[[ChatRequest], Iterable[ChatEvent]]) -> None:
        self.fn = fn
        self.requests: list[ChatRequest] = []

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """`fn`'s events for `request`, `request` kept, ending with one `Done`."""
        raise NotImplementedError("FunctionLLM is plan 006's Track A")

    async def aclose(self) -> None:
        """Nothing to close."""
