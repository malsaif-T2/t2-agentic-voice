"""GroqChat's shell (adapters/groq_chat.py; plan 006, Block 0): built from the settings or in
code on the client every Groq adapter shares, refusing what the settings refuse (GP-20); Groq's
data flow; the key in no repr; and no `groq` type in its signatures (the design's 5.3). Its
stream is tested in test_groq_chat.py and test_groq_chat_checks.py. Nothing leaves the machine:
no request is sent."""

from __future__ import annotations

import asyncio
from typing import Any, get_args, get_type_hints

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.adapters.groq_client import DATA_FLOW
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import ChatModel

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import KEY, SETTING, FakeGroq, groq_settings

VALID: dict[str, Any] = {"api_key": SecretStr(KEY), "base_url": "https://api.groq.com"}
VALID |= {"timeout_s": 8.0}


def test_the_adapter_is_built_from_the_settings_on_the_shared_client() -> None:
    settings = groq_settings().model_copy(update={"llm": LlmSettings(timeout_s=5.0)})
    adapter = GroqChat.from_settings(settings, transport=FakeGroq())
    port: ChatModel = adapter  # mypy checks the port's shape
    assert (port.name, port.data_flow) == ("groq", DATA_FLOW)
    assert repr(adapter) == "GroqChat(base_url='https://api.groq.com', timeout_s=5.0)"
    assert [text for text in (repr(adapter), repr(vars(adapter))) if KEY in text] == []
    asyncio.run(adapter.aclose())

    def modules(hint: object) -> set[str]:  # of a type, and of every type inside it
        return {getattr(hint, "__module__", "")}.union(*(modules(a) for a in get_args(hint)))

    public = [getattr(GroqChat, name) for name in ("__init__", "from_settings", "stream")]
    named = set().union(*(modules(h) for f in public for h in get_type_hints(f).values()))
    assert not [name for name in named if name.split(".")[0] == "groq"]


def test_no_key_in_the_settings_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match=SETTING) as raised:
        GroqChat.from_settings(VoiceSettings(env="test"))
    assert raised.value.details == {"setting": SETTING}


@pytest.mark.parametrize(
    ("given", "setting"),
    [
        ({"api_key": SecretStr("made up")}, SETTING),
        ({"base_url": "http://api.groq.com"}, "T2V_GROQ__BASE_URL"),
        ({"timeout_s": 0.0}, "T2V_LLM__TIMEOUT_S"),
    ],
)
def test_built_in_code_it_refuses_what_settings_refuse(given: dict[str, Any], setting: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqChat(**(VALID | given))
    assert str(raised.value.details["setting"]).startswith(setting)
    assert holding("made up", shown(raised.value)) == []
