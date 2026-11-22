"""The providers of a call an app's page chose (api/choice_calls.py; `server.call_choices`, D-140):
each chosen speech-to-text and chat adapter is built once, reused by later calls, and closed with
the runtime, never the runtime's own; a model of the runtime's provider runs on its adapter; the
talker's factory is built on the chosen settings; a voice is opened on its first choice, once, and
tried again after a failure logged by its kind alone; a choice that cannot be built runs the call
on the server's own; the dev console's choice still reaches its call beside the app's; and a
runtime built from its settings names its speech-to-text's model in the usage (D-140)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.api import choice_calls
from t2_agentic_voice.api.choices_route import VOICE_UNAVAILABLE
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.provider_keys import ElevenLabsSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.choice_support import (
    ELEVEN_KEY,
    OPTIONS,
    Built,
    FakeChat,
    choice_settings,
)
from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    PREFIX,
    FakeIdentity,
    FakePhraseCache,
    Harness,
    joined,
    offered,
    post,
    serving,
)
from tests.t2_agentic_voice.fakes import FakeCalls

pytestmark = pytest.mark.usefixtures("patched_stores")

TALKER = VoiceAgent(
    name="talker", languages=[Language.english(greeting="Hello.")], instructions="Be brief."
)


def _harness(settings: VoiceSettings, built: Built, **given: Any) -> Harness:
    return Harness(settings, call_options=OPTIONS, choice_builders=built.builders(), **given)


async def _choose(
    http: httpx.AsyncClient, call_id: str, secret: str, **ids: object
) -> httpx.Response:
    return await post(http, "/choices", {"call_id": call_id, "offer_secret": secret, **ids})


def _lookup(harness: Harness) -> Any:
    return harness.built[-1]["chosen"]


def test_each_chosen_provider_is_built_once_reused_and_closed_never_the_runtimes(
    tmp_path: Path,
) -> None:
    built, chat = Built(), FakeChat("runtime-chat")
    harness = _harness(choice_settings(tmp_path), built, agent=TALKER, chat=chat)
    caller = Caller(subject="s")

    async def scene() -> None:
        async with serving(harness.app()) as http:
            taken = []
            for ids in (
                {"stt": "scribe", "model": "gpt-5.5"},
                {"stt": "scribe", "model": "gpt-5.5"},
                {"model": "gpt-5.5", "voice": "eleven"},
                {"voice": "eleven"},
            ):
                call_id, secret = await joined(http)
                assert (await _choose(http, call_id, secret, **ids)).status_code == 204
                taken.append(_lookup(harness)(call_id))
            first, second, third, fourth = taken
            assert first is second  # one combination, built once
            assert len(built.stts) == 1 and first.stt is built.stts[0][1]
            assert len(built.chats) == 1 and first.chat is built.chats[0][1]
            assert third.chat is first.chat  # one adapter per provider
            assert built.chats[0][0].llm.provider == "openai"
            assert fourth.chat is chat  # a model of the runtime's provider: its own adapter
            talker = first.talker(TalkerCall(call_id="c", caller=caller, language="en"), 0)
            assert isinstance(talker, ChatTalker) and talker.model is first.chat
            assert talker.settings.llm.model == "gpt-5.5" and talker.settings is first.settings
            assert first.stt_model == "scribe_v3" and fourth.stt_model is None
            assert len(built.ttss) == 1 and third.tts is fourth.tts  # the voice opened once
            folder = tmp_path / "var" / "talker" / "choices" / "eleven" / "clauses"
            assert folder.is_dir()

    asyncio.run(scene())
    assert built.stts[0][1].closed and built.chats[0][1].closed and built.ttss[0][1].closed
    assert all(stt is not harness.stt for _, stt in built.stts)
    assert chat.closed  # the runtime's own, closed once by the runtime itself


def test_a_voice_is_opened_on_its_first_choice_and_tried_again_after_a_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    built = Built()
    harness = _harness(choice_settings(tmp_path), built)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            started = len(FakePhraseCache.built)
            FakePhraseCache.failure = ProviderError("rejected", False, details={"x": "secret-4471"})
            call_id, secret = await joined(http)
            failed = await _choose(http, call_id, secret, voice="bayan")
            assert (failed.status_code, failed.json()["message"]) == (400, VOICE_UNAVAILABLE)
            assert _lookup(harness)(call_id) is None
            FakePhraseCache.failure = None
            assert (await _choose(http, call_id, secret, voice="bayan")).status_code == 204
            other, other_secret = await joined(http)
            assert (await _choose(http, other, other_secret, voice="bayan")).status_code == 204
            assert len(FakePhraseCache.built) - started == 2  # failed once, then opened once
            assert FakePhraseCache.built[-1].folder == tmp_path / "var" / "echo" / "phrases"
            one, two = _lookup(harness)(call_id), _lookup(harness)(other)
            assert one.tts is two.tts and one.phrases is FakePhraseCache.built[-1]
            assert one.settings.tts.provider == "telnyx"

    asyncio.run(scene())
    (line,) = [r for r in caplog.records if r.getMessage() == "call_voice_unavailable"]
    assert getattr(line, FIELDS) == {"voice": "bayan", "failure": "rejected"}
    assert holding("secret-4471", shown(caplog=caplog)) == []
    assert all(tts.closed for _, tts in built.ttss)


def test_a_choice_that_cannot_be_built_runs_on_the_servers_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    harness = _harness(choice_settings(tmp_path), Built())

    def failing(*args: object, **kwargs: object) -> object:
        raise ConfigurationError("The key file is gone. FIX: put it back.")

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            assert (await _choose(http, call_id, secret, stt="scribe")).status_code == 204
            monkeypatch.setattr(choice_calls, "settings_of", failing)
            assert _lookup(harness)(call_id) is None
            assert harness.runtime.call_choice(call_id) is None
            assert (await offered(http, call_id, secret)).status_code == 200

    asyncio.run(scene())
    assert "call_choice_failed" in caplog.text


def test_the_dev_consoles_choice_still_reaches_its_call_beside_the_apps(tmp_path: Path) -> None:
    server = ServerSettings(call_choices=True, dev_page=True)
    harness = _harness(choice_settings(tmp_path, server=server), Built())
    turbo = {"provider": "groq", "model": "whisper-large-v3-turbo", "live_language": "session"}

    async def scene() -> None:
        app = harness.app()
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7860") as http,
        ):
            assert (await http.get(PREFIX + "/choices")).status_code == 200
            assert (await http.get(PREFIX + "/dev/stt")).status_code == 200
            dev, dev_secret = await joined(http)
            body = {"call_id": dev, "offer_secret": dev_secret, **turbo}
            assert (await post(http, "/dev/stt", body)).status_code == 204
            taken = _lookup(harness)(dev)
            assert taken is not None and taken.settings.stt.model == "whisper-large-v3-turbo"
            both, both_secret = await joined(http)
            body = {"call_id": both, "offer_secret": both_secret, **turbo}
            assert (await post(http, "/dev/stt", body)).status_code == 204
            assert (await _choose(http, both, both_secret, stt="scribe")).status_code == 204
            app_wins = _lookup(harness)(both)
            assert app_wins.settings.stt.provider == "elevenlabs"
            assert _lookup(harness)(both) is None  # both taken

    asyncio.run(scene())


def test_a_runtime_built_from_its_settings_names_its_stt_model_in_the_usage(
    tmp_path: Path,
) -> None:
    """D-140, the usage's name: the runtime that builds its providers from the settings hands its
    calls the model its speech-to-text hears with, Scribe's under `stt.provider = "elevenlabs"`."""
    given: list[dict[str, Any]] = []

    def calls(**kwargs: Any) -> FakeCalls:
        given.append(kwargs)
        return FakeCalls()

    settings = choice_settings(
        tmp_path,
        on=False,
        stt=SttSettings(provider="elevenlabs"),
        tts=TtsSettings(provider="groq"),
        elevenlabs=ElevenLabsSettings(api_key=SecretStr(ELEVEN_KEY)),
    )
    runtime = VoiceRuntime(AGENT, settings=settings, identity=FakeIdentity(), _calls=calls)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(runtime.router(), prefix=PREFIX)

    async def scene() -> None:
        async with serving(app):
            pass

    asyncio.run(scene())
    assert given[-1]["stt_model"] == "scribe_v3"
