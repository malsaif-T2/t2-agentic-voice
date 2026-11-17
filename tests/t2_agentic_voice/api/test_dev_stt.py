"""The dev console's choice of speech-to-text (api/stt_choices.py, api/stt_calls.py,
api/dev_stt.py; the owner, 2026-11-16): the menu lists each provider whose key is set, Groq's
always, with its models and the language modes, and never a key or a key's file; a call's
choice is held to that closed set, taken once by that call's offer and by no other; a call
with no choice, and every call of a runtime with no dev page, runs as before (GP-18); the
choice is taken on the console's routes alone, never through `t2v/1`; and the console's records
name who heard each turn."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from t2_agentic_voice.adapters import elevenlabs_stt
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
from t2_agentic_voice.api.dev_feed import DevFeed
from t2_agentic_voice.api.dev_stt import NOT_OFFERED
from t2_agentic_voice.api.providers import stt_kinds
from t2_agentic_voice.api.stt_calls import CallStts
from t2_agentic_voice.api.stt_choices import SttChoice, chosen_settings, menu_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallStarted, TurnMetrics, UserTurnEnded
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.provider_keys import ElevenLabsSettings, SonioxSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.stt import SttModel, SttProvider, SttSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.runtime_support import (
    LOOPBACK,
    PREFIX,
    TOKEN,
    Harness,
    dev_settings,
    offered,
    post,
)

pytestmark = pytest.mark.usefixtures("patched_stores")

KEY = "sk_made-up-elevenlabs-key-0123456789abcdef"
GROQ_KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"
FILE_KEY = "made-up-soniox-key-0123456789abcdef"
LOCAL = "http://127.0.0.1:7860"
AT = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TURBO = {"provider": "groq", "model": "whisper-large-v3-turbo", "live_language": "auto"}
SCRIBE = {"provider": "elevenlabs", "model": "scribe_v3", "live_language": "session"}


def _settings(tmp_path: Path, *, dev_page: bool = True, **groups: Any) -> VoiceSettings:
    """Settings on Groq's Whisper unless a test names its own `stt`: the menu's rules are the
    same whatever the default provider is (D-105 made it ElevenLabs')."""
    groups.setdefault("stt", SttSettings(provider="groq"))
    return dev_settings(tmp_path, server=ServerSettings(dev_page=dev_page), **groups)


def _keyed(tmp_path: Path) -> VoiceSettings:
    """ElevenLabs' key inline, Soniox's in a file outside the repository."""
    key_file = tmp_path / "soniox.key"
    key_file.write_text(FILE_KEY, encoding="utf-8")
    return _settings(
        tmp_path,
        elevenlabs=ElevenLabsSettings(api_key=SecretStr(KEY)),
        soniox=SonioxSettings(api_key_file=key_file),
    )


@asynccontextmanager
async def _serving(
    app: FastAPI, *, peer: tuple[str, int] = LOOPBACK, base: str = LOCAL
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=peer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url=base) as http,
    ):
        yield http


async def _joined(http: httpx.AsyncClient) -> tuple[str, str]:
    answer = await post(http, "/join", {"token": TOKEN, "protocol": 1})
    assert answer.status_code == 200, answer.text
    return answer.json()["call_id"], answer.json()["offer_secret"]


async def _choose(
    http: httpx.AsyncClient, call_id: str, secret: str, choice: dict[str, str]
) -> httpx.Response:
    return await post(http, "/dev/stt", {"call_id": call_id, "offer_secret": secret, **choice})


def _lookup(harness: Harness) -> Any:
    """The lookup of each call's choice the runtime handed voice's calls."""
    return harness.built[-1]["chosen"]


def test_every_provider_a_setting_names_has_its_kind_and_its_adapters_model() -> None:
    kinds = stt_kinds()
    assert list(kinds) == list(get_args(SttProvider))
    assert kinds["groq"].models == get_args(SttModel)
    assert kinds["elevenlabs"].models == (elevenlabs_stt.MODEL,)
    assert all(kind.models and kind.key_group for kind in kinds.values())


def test_the_menu_lists_each_provider_with_a_key_and_never_a_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    alone = menu_of(_settings(tmp_path), classifier=False)
    assert [(o.provider, o.models) for o in alone.providers] == [
        ("groq", ("whisper-large-v3", "whisper-large-v3-turbo"))
    ]
    assert alone.live_languages == ("session", "auto", "detected", "hinted", "single")
    assert alone.default == SttChoice(
        provider="groq", model="whisper-large-v3", live_language="session"
    )
    caplog.set_level(logging.DEBUG)
    keyed = menu_of(_keyed(tmp_path), classifier=True)
    assert [o.provider for o in keyed.providers] == ["groq", "elevenlabs", "soniox"]
    assert {o.provider: o.models for o in keyed.providers}["elevenlabs"] == ("scribe_v3",)
    assert "classified" in keyed.live_languages
    text = keyed.model_dump_json()
    surfaces = {"menu": text, **shown(caplog=caplog)}
    for secret in (KEY, FILE_KEY, str(tmp_path / "soniox.key"), "soniox.key"):
        assert holding(secret, surfaces) == []


def test_a_key_file_that_cannot_be_read_leaves_its_provider_out_unnamed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "nowhere" / "soniox.key"
    settings = _settings(tmp_path, soniox=SonioxSettings(api_key_file=missing))
    caplog.set_level(logging.DEBUG)
    menu = menu_of(settings, classifier=False)
    assert [o.provider for o in menu.providers] == ["groq"]
    assert holding(str(missing), shown(caplog=caplog)) == []
    assert "stt_choice_unavailable" in caplog.text


def test_the_settings_own_provider_and_model_are_the_default_and_listed_first(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, stt=SttSettings(provider="groq", model="whisper-large-v3-turbo"))
    menu = menu_of(settings, classifier=False)
    assert menu.providers[0].models == ("whisper-large-v3-turbo", "whisper-large-v3")
    assert menu.default.model == "whisper-large-v3-turbo"


def test_a_chosen_calls_settings_change_its_speech_to_text_alone(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    chosen = chosen_settings(settings, SttChoice(**TURBO))
    assert (chosen.stt.provider, chosen.stt.model, chosen.stt.live_language) == (
        "groq",
        "whisper-large-v3-turbo",
        "auto",
    )
    assert chosen.model_dump(exclude={"stt"}) == settings.model_dump(exclude={"stt"})
    assert chosen.stt.timeout_s == settings.stt.timeout_s and chosen.prefix == settings.prefix
    assert settings.stt.model == "whisper-large-v3"  # the runtime's own, unchanged


@pytest.mark.parametrize(
    "choice",
    [
        {"provider": "openai", "model": "whisper-large-v3", "live_language": "session"},
        SCRIBE,  # no ElevenLabs key set
        {"provider": "groq", "model": "scribe_v3", "live_language": "session"},
        {"provider": "groq", "model": "whisper-large-v3", "live_language": "classified"},
        {"provider": "groq", "model": "whisper-large-v3", "live_language": "klingon"},
    ],
)
def test_a_choice_outside_the_menu_is_refused_plainly(
    choice: dict[str, str], tmp_path: Path
) -> None:
    harness = Harness(_settings(tmp_path))

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            call_id, secret = await _joined(http)
            answer = await _choose(http, call_id, secret, choice)
            assert answer.status_code == 400
            assert answer.json()["code"] == "invalid_request"
            assert answer.json()["message"] == NOT_OFFERED
            assert choice["model"] not in answer.text and choice["provider"] not in answer.text
            assert (await offered(http, call_id, secret)).status_code == 200
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_one_calls_choice_is_taken_once_by_its_offer_and_by_no_other(tmp_path: Path) -> None:
    harness = Harness(_settings(tmp_path, groq=GroqSettings(api_key=SecretStr(GROQ_KEY))))

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            one, one_secret = await _joined(http)
            other, _ = await _joined(http)
            assert (await _choose(http, one, one_secret, TURBO)).status_code == 204
            assert (await _choose(http, other, one_secret, TURBO)).status_code == 403
            lookup = _lookup(harness)
            assert lookup(other) is None
            taken = lookup(one)
            assert taken is not None and lookup(one) is None  # once
            assert (taken.settings.stt.model, taken.settings.stt.live_language) == (
                "whisper-large-v3-turbo",
                "auto",
            )
            assert taken.stt is not harness.stt
            assert harness.runtime._settings.stt.model == "whisper-large-v3"
            assert (await offered(http, one, one_secret)).status_code == 200
            late = await _choose(http, one, one_secret, TURBO)
            assert (late.status_code, late.json()["code"]) == (409, "already_offered")

    asyncio.run(scene())


def test_the_settings_own_choice_is_kept_as_none(tmp_path: Path) -> None:
    harness = Harness(_settings(tmp_path))
    own = {"provider": "groq", "model": "whisper-large-v3", "live_language": "session"}

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            call_id, secret = await _joined(http)
            assert (await _choose(http, call_id, secret, TURBO)).status_code == 204
            assert (await _choose(http, call_id, secret, own)).status_code == 204
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_with_no_dev_page_voice_is_given_no_lookup_and_the_route_is_absent(
    tmp_path: Path,
) -> None:
    harness = Harness(_settings(tmp_path, dev_page=False))

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            call_id, secret = await _joined(http)
            answer = await _choose(http, call_id, secret, TURBO)
            menu = await http.get(PREFIX + "/dev/stt")
        assert answer.status_code == 404 and menu.status_code == 404
        assert "chosen" not in harness.built[-1]  # today's calls, as before (GP-18)

    asyncio.run(scene())


@pytest.mark.parametrize(
    ("peer", "base"),
    [("192.0.2.7", LOCAL), ("127.0.0.1", "http://t2v.test")],  # another machine; a name
)
def test_only_this_machine_by_a_loopback_name_may_choose(
    peer: str, base: str, tmp_path: Path
) -> None:
    harness = Harness(_settings(tmp_path))

    async def scene() -> None:
        async with _serving(harness.app(), peer=(peer, 50000), base=base) as http:
            call_id, secret = await _joined(http)
            answer = await _choose(http, call_id, secret, TURBO)
            menu = await http.get(PREFIX + "/dev/stt")
            assert (answer.status_code, menu.status_code) == (404, 404)
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


@pytest.mark.parametrize("field", ["stt", "provider", "stt_provider", "dev_stt"])
def test_a_join_or_an_offer_carrying_a_choice_is_refused(field: str, tmp_path: Path) -> None:
    harness = Harness(_settings(tmp_path))

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            joined = await post(http, "/join", {"token": TOKEN, "protocol": 1, field: TURBO})
            assert (joined.status_code, joined.json()["code"]) == (400, "invalid_request")
            call_id, secret = await _joined(http)
            body = {"call_id": call_id, "sdp": "v=0", "type": "offer", "offer_secret": secret}
            offer = await post(http, "/offer", {**body, field: TURBO})
            assert (offer.status_code, offer.json()["code"]) == (400, "invalid_request")
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_the_menu_route_lists_the_choices_and_a_bad_body_is_refused(tmp_path: Path) -> None:
    harness = Harness(_keyed(tmp_path))

    async def scene() -> None:
        async with _serving(harness.app()) as http:
            menu = await http.get(PREFIX + "/dev/stt")
            call_id, secret = await _joined(http)
            odd = await _choose(http, call_id, secret, {**TURBO, "key": KEY})
        assert menu.status_code == 200 and menu.headers["cache-control"] == "no-store"
        providers = [option["provider"] for option in menu.json()["providers"]]
        assert providers == ["groq", "elevenlabs", "soniox"]
        assert KEY not in menu.text and FILE_KEY not in menu.text and "soniox.key" not in menu.text
        assert (odd.status_code, odd.json()["code"]) == (400, "invalid_request")
        assert KEY not in odd.text

    asyncio.run(scene())


def test_a_chosen_provider_is_built_once_and_closed_with_the_runtime(tmp_path: Path) -> None:
    stts = CallStts(_keyed(tmp_path))

    async def scene() -> None:
        await stts.open(classifier=False)
        assert stts.choose("call-1", SttChoice(**SCRIBE))
        assert stts.choose("call-2", SttChoice(**SCRIBE))
        first, second = stts.take("call-1"), stts.take("call-2")
        assert first is not None and second is not None
        assert isinstance(first.stt, ElevenLabsSTT) and first.stt is second.stt
        assert first.settings.stt.provider == "elevenlabs"
        assert stts.heard_by("call-1") == {"provider": "elevenlabs", "model": "scribe_v3"}
        assert stts.heard_by("call-3") == {"provider": "groq", "model": "whisper-large-v3"}
        await stts.aclose()
        assert first.stt._http.is_closed

    asyncio.run(scene())


def test_the_feed_names_who_heard_each_turn_and_keeps_it_saved(tmp_path: Path) -> None:
    stts = CallStts(_keyed(tmp_path))
    folder = tmp_path / "feed"

    async def scene() -> list[dict[str, Any]]:
        await stts.open(classifier=False)
        stts.choose("c-1", SttChoice(**SCRIBE))
        stts.take("c-1")
        feed = DevFeed(folder=folder, hearers=stts)
        await feed.observe(CallStarted(call_id="c-1", at=AT))
        await feed.observe(UserTurnEnded(call_id="c-1", turn_id=0, at=AT, heard="hello"))
        await feed.observe(TurnMetrics(call_id="c-1", turn_id=0, at=AT, stt_ms=640.0))
        await feed.observe(UserTurnEnded(call_id="c-2", turn_id=0, at=AT, heard="hi"))
        await stts.aclose()
        restarted = DevFeed(folder=folder)
        await restarted.ready()
        return restarted.after(0)

    records = asyncio.run(scene())
    named = [(r["call_id"], r["type"], r.get("heard_by")) for r in records]
    scribe = {"provider": "elevenlabs", "model": "scribe_v3"}
    assert named == [
        ("c-1", "CallStarted", None),
        ("c-1", "UserTurnEnded", scribe),
        ("c-1", "TurnMetrics", scribe),
        ("c-2", "UserTurnEnded", {"provider": "groq", "model": "whisper-large-v3"}),
    ]
    saved = (folder / "c-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(saved[2])["heard_by"] == scribe and "heard_by" not in json.loads(saved[0])
