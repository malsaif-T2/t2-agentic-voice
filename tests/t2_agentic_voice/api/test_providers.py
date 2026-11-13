"""The composition of the talker (api/providers.py, agent/talker.py's `chat_talkers`,
voice/talkers.py, voice/calls.py; plan 006):
the providers gain the chat model, Groq's from the settings; each call of an agent that runs
the talker gets its own `ChatTalker`, on the runtime's chat model, one tool runner of the agent's
tools and the call's clock; an agent that runs the echo gets none; voice's entry point refuses an
agent that runs the talker with no chat model; and the runtime hands its calls the factory and
closes the chat model when it stops."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr
from t2_agentic_voice.actions.agent_tools import tools_of
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.adapters import groq_tts
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall, chat_talkers
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.session import SessionSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.talkers import talker_for, talks

from tests.t2_agentic_voice.api.runtime_support import FakeIdentity, dev_settings, serving
from tests.t2_agentic_voice.fakes import (
    FakeCalls,
    FakeClock,
    FakePhrases,
    FakeSpeechToText,
    FakeTextToSpeech,
)
from tests.t2_agentic_voice.language_fakes import FakeLanguageClassifier
from tests.t2_agentic_voice.session_fakes import AGENT as ECHO

pytestmark = pytest.mark.usefixtures("patched_stores")
KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"


class _Query(BaseModel):
    query: str


SEARCH = Tool(
    name="search_help", description="Search the help pages.", parameters=_Query, function=print
)
AGENT = VoiceAgent(
    name="talker",
    languages=[Language.english(greeting="Hello.")],
    instructions="Answer briefly.",
    tools=[SEARCH],
)


class _Chat:
    """A chat model no test asks; it keeps whether it was closed."""

    name = "fake-chat"
    data_flow = FAKE_DATA_FLOW

    def __init__(self) -> None:
        self.closed = False

    def stream(self, request: object) -> AsyncIterator[Any]:
        raise AssertionError("no request")

    async def aclose(self) -> None:
        self.closed = True


class _Tts:
    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> _Tts:
        return cls()


def test_the_providers_from_the_settings_hold_groqs_chat_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(groq_tts, "GroqTTS", _Tts)
    settings = dev_settings(tmp_path, groq=GroqSettings(api_key=SecretStr(KEY)))
    providers = Providers.from_settings(settings)
    assert isinstance(providers.chat, GroqChat)
    chat = _Chat()
    assert providers.replace(chat=chat).chat is chat and providers.replace().chat is providers.chat
    assert Providers(stt=providers.stt, tts=providers.tts).chat is None
    asyncio.run(providers.stt.aclose())
    asyncio.run(providers.chat.aclose())


def test_each_call_of_an_instructed_agent_gets_a_talker_of_its_own(
    settings: VoiceSettings,
) -> None:
    chat, clock = _Chat(), FakeClock()
    factory = chat_talkers(AGENT, settings, chat)
    assert factory is not None
    call = TalkerCall(call_id="c-1", caller=Caller(subject="s-1"), language="en")
    first, second = factory(call, clock), factory(call, clock)
    assert isinstance(first, ChatTalker) and isinstance(second, ChatTalker)
    assert first is not second
    assert (first.model, first.settings, first.call, first.clock) == (chat, settings, call, clock)
    assert first.runner is second.runner and first.runner.tools == (SEARCH,)  # one runner
    assert chat_talkers(ECHO, settings, chat) is None
    assert chat_talkers(AGENT, settings, None) is None
    echo = settings.model_copy(update={"session": SessionSettings(mode="echo")})
    assert chat_talkers(AGENT, echo, chat) is None  # a team's first audio check


def test_a_tool_the_library_cannot_run_is_refused() -> None:
    class _Declared:
        name, description, progress = "lookup", "Look up.", None

    agent = AGENT.model_copy(update={"tools": (_Declared(),)})
    with pytest.raises(ConfigurationError, match="FIX: build each with @tool"):
        tools_of(agent)


def test_voice_refuses_an_agent_that_runs_the_talker_with_no_chat_model(
    settings: VoiceSettings,
) -> None:
    given: dict[str, Any] = {
        "settings": settings,
        "stt": FakeSpeechToText(),
        "tts": FakeTextToSpeech(),
        "phrases": FakePhrases(),
        "tracing": Tracing(),
        "emit": lambda event: None,
    }
    with pytest.raises(ConfigurationError, match=r"no chat model was given.*FIX:"):
        VoiceCalls(agent=AGENT, **given)
    assert not talks(ECHO, settings, None)
    built: list[TalkerCall] = []
    talker: Any = object()

    def factory(call: TalkerCall, clock: Any) -> Any:
        built.append(call)
        return talker

    calls = VoiceCalls(agent=AGENT, talker=factory, **given)
    assert calls._talker is factory
    english, caller = AGENT.languages[0], Caller(subject="s")
    found = talker_for(factory, call_id="c-2", caller=caller, language=english, clock=FakeClock())
    assert found is talker
    assert built == [TalkerCall(call_id="c-2", caller=caller, language="en")]
    assert talker_for(None, call_id="c", caller=caller, language=english, clock=FakeClock()) is None


def test_the_runtime_hands_its_calls_the_talkers_and_closes_the_chat_model(
    tmp_path: Path,
) -> None:
    chat, built = _Chat(), list[dict[str, Any]]()
    fake = FakeCalls()

    def calls(**given: Any) -> Any:
        built.append(given)
        return fake

    runtime = VoiceRuntime(
        AGENT,
        settings=dev_settings(tmp_path),
        identity=FakeIdentity(),
        providers=Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech(), chat=chat),
        _calls=calls,
    )
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(runtime.router(), prefix="/voice")

    async def scene() -> None:
        async with serving(app):
            assert not chat.closed

    asyncio.run(scene())
    assert chat.closed
    (given,) = built
    assert given["chat"] is chat  # the model of an uncertain overlap, D-069
    talker = given["talker"](TalkerCall(call_id="c", caller=Caller(subject="s"), language="en"), 0)
    assert isinstance(talker, ChatTalker) and talker.model is chat


def test_the_providers_build_a_classifier_only_under_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The classifier (D-086): Silero's by default, ECAPA's when named, each on the settings'
    folder and threads, built with no IO (its files are checked when the runtime loads it);
    `replace` keeps it, or puts another in its place."""
    from t2_agentic_voice.adapters.ecapa_language import EcapaLanguage
    from t2_agentic_voice.adapters.silero_language import SileroLanguage
    from t2_agentic_voice.core.settings.stt import SttSettings

    monkeypatch.setattr(groq_tts, "GroqTTS", _Tts)
    groq = GroqSettings(api_key=SecretStr(KEY))
    plain = Providers.from_settings(dev_settings(tmp_path, groq=groq))
    assert plain.classifier is None
    folder = tmp_path / "models"
    for name, kind in (("silero", SileroLanguage), ("ecapa", EcapaLanguage)):
        stt = SttSettings(
            live_language="classified",
            classifier=name,  # type: ignore[arg-type]
            classifier_dir=folder,
            classifier_threads=3,
        )
        providers = Providers.from_settings(dev_settings(tmp_path, groq=groq, stt=stt))
        built = providers.classifier
        assert isinstance(built, kind) and (built.folder, built.threads) == (folder, 3)
        assert providers.replace().classifier is built
        other = FakeLanguageClassifier()
        replaced = providers.replace(classifier=other)
        assert replaced.classifier is other and replaced.stt is providers.stt
        _closed(providers)
    _closed(plain)


def _closed(providers: Providers) -> None:
    asyncio.run(providers.stt.aclose())
    if providers.chat is not None:
        asyncio.run(providers.chat.aclose())
