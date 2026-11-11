"""The runtime (api/runtime.py): built with no IO, refusing settings its `env` refuses even in a
copy that skipped validation; its router refusing `env` test and a runtime with no identity
source, but under `t2v dev`; its lifespan opening each part in order and closing each, on the way
out and after a failure at start, the lock released; and the providers built from the
settings."""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters import groq_tts
from t2_agentic_voice.adapters.dev_identity import DevIdentity
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.api.lockfile import LockFile
from t2_agentic_voice.api.runtime import (
    FORGOTTEN_KEPT_S,
    SWEEP_PERIOD_S,
    Providers,
    VoiceRuntime,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK

from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    FakeIdentity,
    FakePhraseCache,
    FakeUsedTokens,
    Harness,
    dev_settings,
    joined,
    offered,
    serving,
)
from tests.t2_agentic_voice.core.test_settings_checks import CHECKS
from tests.t2_agentic_voice.fakes import FakeCalls, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.language_fakes import FakeLanguageClassifier

pytestmark = pytest.mark.usefixtures("patched_stores")
KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"

UNSAFE = [
    (location, value, env)
    for location, value, envs in CHECKS
    for env in ("staging", "prod")
    if env in envs
]


@pytest.mark.parametrize(("location", "value", "env"), UNSAFE)
def test_a_copy_its_env_refuses_is_refused_at_construction(
    location: tuple[str, str], value: object, env: str, settings: VoiceSettings
) -> None:
    """Every check that holds in prod holds in staging too, on a copy that skipped validation."""
    group, name = location
    changed = getattr(settings, group).model_copy(update={name: value})
    unsafe = settings.model_copy(update={"env": env, group: changed})
    with pytest.raises(ConfigurationError) as raised:
        VoiceRuntime(AGENT, settings=unsafe)
    assert f"env={env} refuses" in raised.value.message


def test_a_test_gives_the_runtime_its_calls_and_its_clock() -> None:
    parameters = inspect.signature(VoiceRuntime).parameters
    defaults = [(parameters[name].kind, parameters[name].default) for name in ("_calls", "_clock")]
    keyword = inspect.Parameter.KEYWORD_ONLY
    assert defaults == [(keyword, VoiceCalls), (keyword, SYSTEM_CLOCK)]
    assert FORGOTTEN_KEPT_S == 60.0


def test_providers_replace_only_what_is_given() -> None:
    stt, tts = cast(SpeechToText, object()), cast(TextToSpeech, object())
    other_stt, other_tts = cast(SpeechToText, object()), cast(TextToSpeech, object())
    providers = Providers(stt=stt, tts=tts)
    assert providers.replace() == providers
    assert providers.replace(stt=other_stt) == Providers(stt=other_stt, tts=tts)
    assert providers.replace(tts=other_tts) == Providers(stt=stt, tts=other_tts)


class _Tts:
    built: ClassVar[list[VoiceSettings]] = []

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> _Tts:
        cls.built.append(settings)
        return cls()


def test_the_providers_from_the_settings_are_groqs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(groq_tts, "GroqTTS", _Tts)
    settings = dev_settings(tmp_path, groq=GroqSettings(api_key=SecretStr(KEY)))
    providers = Providers.from_settings(settings)
    assert isinstance(providers.stt, GroqSTT) and isinstance(providers.tts, _Tts)
    assert _Tts.built == [settings]
    asyncio.run(providers.stt.aclose())


def test_a_router_is_refused_under_env_test(settings: VoiceSettings) -> None:
    with pytest.raises(ConfigurationError, match=r"env=test\. FIX:"):
        VoiceRuntime(AGENT, settings=settings).router()


def test_a_router_needs_an_identity_source_but_under_t2v_dev(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = VoiceRuntime(AGENT, settings=dev_settings(tmp_path))
    with pytest.raises(ConfigurationError, match=r"no identity source.*FIX:"):
        runtime.router()
    routes = runtime._router(dev=True).routes
    assert "/dev" in {getattr(route, "path", None) for route in routes}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [
        "dev_identity"
    ]


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_t2v_dev_serves_only_env_dev(env: str, tmp_path: Path) -> None:
    runtime = VoiceRuntime(AGENT, settings=VoiceSettings(env=env), identity=DevIdentity())  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match=f"only env=dev, not env={env}"):
        runtime._router(dev=True)


def test_the_lifespan_opens_each_part_in_order_and_closes_each(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))
    var_dir = harness.settings.storage.var_dir

    async def scene() -> None:
        async with serving(harness.app()):
            assert harness.calls.started == 1 and harness.calls.closed == 0
            with pytest.raises(ConfigurationError, match="Another process holds"):
                LockFile.take(var_dir)
        assert harness.calls.closed == 1
        assert harness.stt.closed and harness.tts.closed

    asyncio.run(scene())
    [cache] = FakePhraseCache.built
    assert (cache.declared, cache.tts, cache.folder) == (
        AGENT,
        harness.tts,
        var_dir / "echo" / "phrases",
    )
    assert FakeUsedTokens.opened == [var_dir / "echo" / "used_tokens.sqlite3"]
    [given] = harness.built
    assert set(given) == {
        *("agent", "settings", "stt", "tts", "phrases", "tracing", "emit", "clock"),
        "action_jobs",
    }
    assert given["action_jobs"] is None  # the echo declares no action
    assert (given["agent"], given["settings"], given["clock"]) == (
        AGENT,
        harness.settings,
        harness.clock,
    )
    assert (given["stt"], given["tts"], given["phrases"]) == (harness.stt, harness.tts, cache)
    assert isinstance(given["tracing"], Tracing)
    LockFile.take(var_dir).release()


def test_a_failure_at_start_closes_what_was_opened(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))
    FakePhraseCache.failure = ProviderError("rate_limited", True)

    async def scene() -> None:
        with pytest.raises(ProviderError):
            async with serving(harness.app()):
                pass  # the start fails first
        assert harness.stt.closed and harness.tts.closed
        assert harness.calls.started == 0
        FakePhraseCache.failure = None
        async with serving(harness.app()):  # the lock was released
            assert harness.calls.started == 1

    asyncio.run(scene())


def test_the_lifespan_runs_once_at_a_time(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()):
            with pytest.raises(ConfigurationError, match="running already"):
                async with harness.runtime.lifespan(object()):
                    pass  # refused first

    asyncio.run(scene())


def test_a_short_secret_in_a_file_stops_the_start(tmp_path: Path) -> None:
    keys = tmp_path / "keys.json"
    keys.write_text('{"k1": "too-short"}', encoding="utf-8")
    harness = Harness(dev_settings(tmp_path, join=JoinSettings(keys_file=keys)))

    async def scene() -> None:
        with pytest.raises(ConfigurationError) as raised:
            async with serving(harness.app()):
                pass  # the start fails first
        assert "T2V_JOIN__KEYS_FILE" in raised.value.message
        assert "too-short" not in raised.value.message and str(keys) not in raised.value.message

    asyncio.run(scene())
    LockFile.take(harness.settings.storage.var_dir).release()


class _Unsweepable(FakeCalls):
    def phase(self, call_id: str) -> Any:
        raise RuntimeError("phase failed")


def test_a_failed_sweep_is_logged_and_the_next_one_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(dev_settings(tmp_path), calls=_Unsweepable())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            await harness.clock.advance(0)
            await offered(http, *(await joined(http)))
            await harness.clock.advance(2 * SWEEP_PERIOD_S)

    asyncio.run(scene())
    failed = [r for r in caplog.records if r.getMessage() == "sweep_failed"]
    assert len(failed) == 2 and all(r.levelno == logging.ERROR for r in failed)


def _classifying(
    tmp_path: Path, classifier: Any, *, agent: Any = AGENT, live: str = "classified"
) -> tuple[VoiceRuntime, list[dict[str, Any]]]:
    """A runtime of `agent` whose providers hold `classifier`, under `stt.live_language` `live`
    (plan 007's Block H), and the arguments its calls were built with."""
    from t2_agentic_voice.core.settings.stt import SttSettings

    built: list[dict[str, Any]] = []

    def calls(**given: Any) -> FakeCalls:
        built.append(given)
        return FakeCalls()

    settings = dev_settings(tmp_path, stt=SttSettings(live_language=live))  # type: ignore[arg-type]
    providers = Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech(), classifier=classifier)
    runtime = VoiceRuntime(
        agent, settings=settings, identity=FakeIdentity(), providers=providers, _calls=calls
    )
    return runtime, built


def _app(runtime: VoiceRuntime) -> Any:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(runtime.router(), prefix="/voice")
    return app


def test_the_classifier_is_loaded_at_start_with_the_agents_codes_and_closed_once(
    tmp_path: Path,
) -> None:
    classifier = FakeLanguageClassifier()
    runtime, built = _classifying(tmp_path, classifier)

    async def scene() -> None:
        async with serving(_app(runtime)):
            assert classifier.loaded == [("en", "ar")] and classifier.closed == 0

    asyncio.run(scene())
    assert classifier.closed == 1
    (given,) = built
    assert given["classifier"] is classifier


def test_no_classifier_runs_under_session_nor_for_an_agent_of_one_code(tmp_path: Path) -> None:
    english = AGENT.model_copy(update={"languages": AGENT.languages[:1]})
    for agent, live in ((AGENT, "session"), (english, "classified")):
        classifier = FakeLanguageClassifier()
        runtime, built = _classifying(tmp_path / live, classifier, agent=agent, live=live)

        async def scene(app: Any) -> None:
            async with serving(app):
                pass

        asyncio.run(scene(_app(runtime)))
        assert classifier.loaded == [] and classifier.closed == 1
        assert "classifier" not in built[0]


def test_classified_with_no_classifier_dir_is_refused_at_start_with_a_fix(tmp_path: Path) -> None:
    from t2_agentic_voice.adapters.silero_language import SileroLanguage

    runtime, built = _classifying(tmp_path, SileroLanguage(None, threads=2))

    async def scene() -> None:
        with pytest.raises(ConfigurationError, match=r"stt\.classifier_dir is not set.*FIX"):
            async with serving(_app(runtime)):
                pass  # the start fails first

    asyncio.run(scene())
    assert built == []  # no call was built
