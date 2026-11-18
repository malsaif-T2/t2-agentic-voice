"""The talker's chat provider (D-112): `llm.provider` picks the chat adapter
(api/providers.py's `chat_model`), Groq's by default; under `openai` a `ChatRoute`
(api/chat_route.py) sends the talker's model to OpenAI's adapter and the library's own checks
(the yes rule's, the uncertain overlap's) to Groq's, warms both, closes both and names both in
its data flow; and the settings refuse a model its provider does not serve, or an effort its
model does not take, under the setting's name and its fix. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import get_args

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.adapters.openai_chat import OpenAIChat
from t2_agentic_voice.api.chat_route import ChatRoute
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.llm import EFFORTS, PROVIDER_OF, LlmModel, LlmSettings
from t2_agentic_voice.core.settings.provider_keys import OpenAISettings
from t2_agentic_voice.domain.consent_check import consent_check_request
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatMessage,
    ChatRequest,
    Done,
    TextDelta,
)
from t2_agentic_voice.domain.uncertain_overlaps import uncertain_overlap_request
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW

GROQ_KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"
OPENAI_KEY = "sk-made-up-key-0123456789abcdefghijklmnop"
PREFIX = "T2V_"


class _Chat:
    """A chat model that answers every request with its own name, and counts what it was asked."""

    data_flow = FAKE_DATA_FLOW

    def __init__(self, name: str, *, warm: bool = False, fails: bool = False) -> None:
        self.name, self._warm, self._fails = name, warm, fails
        self.models: list[str] = []
        self.warmed = self.closed = 0

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.models.append(request.model)
        yield TextDelta(text=self.name)
        yield Done(finish_reason="stop")

    def warm(self) -> bool:
        return self._warm

    async def warm_up(self) -> None:
        self.warmed += 1
        if self._fails:
            raise ProviderError("timeout", True)

    async def aclose(self) -> None:
        self.closed += 1


def _request(model: str) -> ChatRequest:
    return ChatRequest(messages=(ChatMessage.user("Hi"),), model=model)


async def _said(route: ChatRoute, model: str) -> list[ChatEvent]:
    return [event async for event in route.stream(_request(model))]


def test_each_request_goes_to_the_provider_of_its_model() -> None:
    openai, groq = _Chat("openai"), _Chat("groq")
    route = ChatRoute(main=("openai", openai), others={"groq": groq})
    check = consent_check_request("-", "-", "-")
    overlap = uncertain_overlap_request("-", "-")
    for request in (check, overlap):
        assert asyncio.run(_said(route, request.model))[0] == TextDelta(text="groq")
    assert asyncio.run(_said(route, "gpt-6-luna"))[0] == TextDelta(text="openai")
    assert asyncio.run(_said(route, "a-model-no-provider-is-named-for"))[0] == TextDelta(
        text="openai"
    )
    assert groq.models == [check.model, overlap.model] == ["openai/gpt-oss-120b"] * 2
    assert openai.models == ["gpt-6-luna", "a-model-no-provider-is-named-for"]
    assert route.name == "openai+groq"


def test_the_route_is_as_warm_as_the_talkers_warms_both_and_closes_both() -> None:
    openai, groq = _Chat("openai", warm=True), _Chat("groq", fails=True)
    route = ChatRoute(main=("openai", openai), others={"groq": groq})
    assert route.warm() is True
    with pytest.raises(ProviderError):
        asyncio.run(route.warm_up())
    assert (openai.warmed, groq.warmed) == (1, 1)  # the other tried, the failure raised after
    asyncio.run(route.aclose())
    assert (openai.closed, groq.closed) == (1, 1)


def test_the_routes_data_flow_names_each_provider_and_what_it_is_sent() -> None:
    route = ChatRoute(main=("openai", _Chat("openai")), others={"groq": _Chat("groq")})
    assert "(the talker's requests)" in route.data_flow.provider
    assert "(the library's own checks)" in route.data_flow.provider


def _keys(**llm: object) -> VoiceSettings:
    return VoiceSettings(
        env="test",
        groq=GroqSettings(api_key=SecretStr(GROQ_KEY)),
        openai=OpenAISettings(api_key=SecretStr(OPENAI_KEY)),
        llm=LlmSettings.model_validate(llm),
    )


def test_groq_stays_the_default_and_openai_is_routed_beside_it() -> None:
    chat = Providers.chat_model(_keys())
    assert isinstance(chat, GroqChat)
    asyncio.run(chat.aclose())
    routed = Providers.chat_model(
        _keys(provider="openai", model="gpt-6-luna", reasoning_effort="none")
    )
    assert isinstance(routed, ChatRoute)
    assert isinstance(routed.route_of("gpt-6-luna"), OpenAIChat)
    assert isinstance(routed.route_of("openai/gpt-oss-120b"), GroqChat)
    asyncio.run(routed.aclose())


def test_openai_with_no_key_names_its_setting() -> None:
    settings = VoiceSettings(
        env="test",
        groq=GroqSettings(api_key=SecretStr(GROQ_KEY)),
        llm=LlmSettings(provider="openai", model="gpt-6-luna", reasoning_effort="none"),
    )
    with pytest.raises(ConfigurationError, match="T2V_OPENAI__API_KEY"):
        Providers.chat_model(settings)


def test_every_model_has_its_provider_and_every_effort_list_a_model() -> None:
    models = set(get_args(LlmModel))
    assert set(PROVIDER_OF) == models and set(EFFORTS) <= models
    assert LlmSettings.provider_of("gpt-5.6-luna") == "openai"
    assert LlmSettings.provider_of("a-model-no-provider-is-named-for") == "groq"


@pytest.mark.parametrize(
    ("values", "named", "fix"),
    [
        (
            {"LLM__MODEL": "gpt-6-luna", "LLM__REASONING_EFFORT": "none"},
            "LLM__MODEL",
            "llm.provider to openai",
        ),
        ({"LLM__PROVIDER": "openai"}, "LLM__MODEL", "one of openai's (gpt-6-luna,"),
        ({"LLM__PROVIDER": "openai", "LLM__MODEL": "gpt-6-luna"}, "LLM__REASONING_EFFORT", "none"),
        ({"LLM__REASONING_EFFORT": "none"}, "LLM__REASONING_EFFORT", "high, low, medium, not"),
    ],
)
def test_a_model_and_provider_or_effort_that_do_not_fit_are_refused_with_the_fix(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str], named: str, fix: str
) -> None:
    monkeypatch.setenv("T2V_ENV", "test")
    for name, value in values.items():
        monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ConfigurationError, match=f"{PREFIX}{named} ") as raised:
        VoiceSettings.from_env()
    assert fix in raised.value.message


def test_an_openai_model_at_effort_none_loads() -> None:
    llm = LlmSettings(provider="openai", model="gpt-6.1-terra", reasoning_effort="none")
    assert (llm.provider, llm.model, llm.reasoning_effort) == ("openai", "gpt-6.1-terra", "none")
