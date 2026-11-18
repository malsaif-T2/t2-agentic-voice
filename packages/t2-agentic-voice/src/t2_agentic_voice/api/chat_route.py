"""The call's chat model when the talker is not on Groq (D-112): `ChatRoute` sends each request
to the adapter of the provider that serves its model (core/settings/llm.py's `PROVIDER_OF`).
So under `llm.provider = "openai"` the talker's requests go to OpenAI, while the library's own
requests of a call, the yes rule's check (D-082) and an uncertain overlap's (D-069), stay on
Groq's gpt-oss-120b, the model they were measured on. A model no provider is named for goes to
the main adapter, the talker's.

- `warm()` is the main adapter's: the talker's requests are the ones a call's first reply
  waits on, so a join warms the route unless the talker's connection is warm
  (voice/join_warmth.py), and the warm flag of the session's own requests reads it too.
- `warm_up()` warms every adapter that takes it, the main one first, and raises the first
  failure once each was tried.
- `aclose()` closes every adapter. `data_flow` names each provider and what it is sent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.llm import PROVIDER_OF, LlmProvider
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatModel, ChatRequest
from t2_agentic_voice.domain.ports.connection_warmth import WarmUp, warm_now
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow


class ChatRoute:
    """A `ChatModel` over one adapter per provider: `main` serves the talker's provider,
    `others` the rest by their provider's name. Close it with `aclose()`."""

    def __init__(
        self, *, main: tuple[LlmProvider, ChatModel], others: Mapping[str, ChatModel]
    ) -> None:
        self._main_provider, self._main = main
        self._routes: dict[str, ChatModel] = dict(others)
        self._routes[self._main_provider] = self._main
        self.name = "+".join([self._main.name, *(model.name for model in others.values())])
        self.data_flow = _joined(self._main, others)

    def __repr__(self) -> str:
        return f"ChatRoute(main={self._main_provider!r}, routes={sorted(self._routes)!r})"

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The answer of the adapter whose provider serves `request.model` (the module's
        docstring), as that adapter streams it."""
        return self.route_of(request.model).stream(request)

    def route_of(self, model: str) -> ChatModel:
        """The adapter a request for `model` goes to."""
        provider = PROVIDER_OF.get(model)
        return self._routes.get(provider, self._main) if provider else self._main

    def warm(self) -> bool:
        """Whether the talker's next request goes out on a kept-alive connection."""
        return warm_now(self._main) is True

    async def warm_up(self) -> None:
        """Warm each adapter that takes it, the main one first; the first ProviderError raised
        once every one was tried."""
        first: ProviderError | None = None
        for model in self._routes_in_order():
            if not isinstance(model, WarmUp):
                continue
            try:
                await model.warm_up()
            except ProviderError as error:
                first = first or error
        if first is not None:
            raise first

    async def aclose(self) -> None:
        """Close every adapter."""
        for model in self._routes_in_order():
            await model.aclose()

    def _routes_in_order(self) -> list[ChatModel]:
        return [self._main, *(m for m in self._routes.values() if m is not self._main)]


def _joined(main: ChatModel, others: Mapping[str, ChatModel]) -> DataFlow:
    """One data flow that names each provider, the talker's first, and its own terms."""
    flows = [("the talker's requests", main.data_flow)] + [
        ("the library's own checks", model.data_flow) for model in others.values()
    ]
    return DataFlow(
        provider=" and ".join(f"{flow.provider} ({what})" for what, flow in flows),
        processed_in="; ".join(f"{flow.provider}: {flow.processed_in}" for _, flow in flows),
        stored_in="; ".join(f"{flow.provider}: {flow.stored_in}" for _, flow in flows),
        retention="; ".join(f"{flow.provider}: {flow.retention}" for _, flow in flows),
    )
