"""A call's speech-to-text, chat model and voice chosen by an app's page (api/choice_calls.py,
api/choices_route.py; `server.call_choices`, the owner, 2026-11-22): a choice is held to the
menu's closed set and refused with a message that names no value sent; it needs the call's ID
and offer secret, before its offer, in a strict body within its cap (an offer sent while its
voice opens leaves it refused and unkept); it is taken once by that call's offer and by no
other; the settings' own is kept as none; with the setting off nothing is mounted and every
call is built as before (GP-18); `t2v/1` carries no choice; and no answer or log line shows a
key, a key's file or a voice's ID. How the chosen providers are built is
test_call_choice_providers.py's."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from t2_agentic_voice.api import choice_calls
from t2_agentic_voice.api.call_options import CallChoice
from t2_agentic_voice.api.choices_route import NOT_OFFERED
from t2_agentic_voice.api.voices import open_voices
from t2_agentic_voice.core.config import VoiceSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.choice_support import (
    ELEVEN_KEY,
    GROQ_KEY,
    KEY_FILE,
    OPENAI_KEY,
    OPTIONS,
    TELNYX_KEY,
    VOICE_IDS,
    Built,
    choice_settings,
)
from tests.t2_agentic_voice.api.runtime_support import (
    PREFIX,
    TOKEN,
    Harness,
    joined,
    offered,
    post,
    serving,
)

pytestmark = pytest.mark.usefixtures("patched_stores")


def _harness(settings: VoiceSettings, built: Built, **given: Any) -> Harness:
    return Harness(settings, call_options=OPTIONS, choice_builders=built.builders(), **given)


async def _choose(
    http: httpx.AsyncClient, call_id: str, secret: str, **ids: object
) -> httpx.Response:
    return await post(http, "/choices", {"call_id": call_id, "offer_secret": secret, **ids})


def _lookup(harness: Harness) -> Any:
    return harness.built[-1]["chosen"]


def test_a_kept_choice_is_taken_once_by_its_offer_and_by_no_other(tmp_path: Path) -> None:
    built = Built()
    harness = _harness(choice_settings(tmp_path), built)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            one, one_secret = await joined(http)
            other, _ = await joined(http)
            assert (await _choose(http, one, one_secret, stt="scribe")).status_code == 204
            assert (await _choose(http, other, one_secret, stt="scribe")).status_code == 403
            lookup = _lookup(harness)
            assert lookup(other) is None
            taken = lookup(one)
            assert taken is not None and lookup(one) is None  # once
            assert taken.settings.stt.provider == "elevenlabs" and taken.stt_model == "scribe_v3"
            assert taken.stt is built.stts[0][1] and taken.tts is None and taken.chat is None
            assert harness.runtime.call_choice(one) == CallChoice(stt="scribe")
            assert harness.runtime.call_choice(other) is None
            assert (await offered(http, one, one_secret)).status_code == 200
            late = await _choose(http, one, one_secret, stt="scribe")
            assert (late.status_code, late.json()["code"]) == (409, "already_offered")

    asyncio.run(scene())


def test_an_offer_sent_while_the_voice_opens_leaves_the_choice_refused_and_unkept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    harness = _harness(choice_settings(tmp_path), Built())
    opening, opened = asyncio.Event(), asyncio.Event()

    async def held(*args: Any, **kwargs: Any) -> Any:
        opening.set()
        await opened.wait()
        return await open_voices(*args, **kwargs)

    monkeypatch.setattr(choice_calls, "open_voices", held)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            choosing = asyncio.create_task(_choose(http, call_id, secret, voice="bayan"))
            await opening.wait()
            assert (await offered(http, call_id, secret)).status_code == 200
            opened.set()
            late = await choosing
            assert (late.status_code, late.json()["code"]) == (409, "already_offered")
            assert _lookup(harness)(call_id) is None
            assert harness.runtime.call_choice(call_id) is None

    asyncio.run(scene())
    assert "call_choice_made" not in caplog.text


@pytest.mark.parametrize(
    ("ids", "keys"),
    [
        ({"stt": "klingon"}, True),
        ({"model": "scribe"}, True),  # a known id in the wrong group
        ({"voice": "whisper"}, True),
        ({"stt": "scribe"}, False),  # left out of the menu: no ElevenLabs key
        ({"model": "gpt-5.5"}, False),  # no OpenAI key
    ],
)
def test_a_choice_outside_the_menu_is_refused_naming_no_value(
    ids: dict[str, str], keys: bool, tmp_path: Path
) -> None:
    harness = _harness(choice_settings(tmp_path, keys=keys), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            answer = await _choose(http, call_id, secret, **ids)
            assert (answer.status_code, answer.json()["code"]) == (400, "invalid_request")
            assert answer.json()["message"] == NOT_OFFERED
            assert all(value not in answer.text for value in ids.values())
            assert (await offered(http, call_id, secret)).status_code == 200
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_a_body_too_large_not_json_or_not_a_choice_is_refused_with_no_echo(
    tmp_path: Path,
) -> None:
    harness = _harness(choice_settings(tmp_path), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            base = {"call_id": call_id, "offer_secret": secret}
            big = json.dumps({**base, "stt": "w"}) + " " * 1025
            over = await http.post(
                PREFIX + "/choices", content=big, headers={"content-type": "application/json"}
            )
            declared = await http.post(
                PREFIX + "/choices",
                content=b"{}",
                headers={"content-type": "application/json", "content-length": "1025"},
            )
            plain = await http.post(
                PREFIX + "/choices",
                content=json.dumps(base),
                headers={"content-type": "text/plain"},
            )
            extra = await _choose(http, call_id, secret, stt="whisper", key=ELEVEN_KEY)
            number = await _choose(http, call_id, secret, stt=7)
            odd = await _choose(http, call_id, secret, voice="<b>x</b>")
            assert (over.status_code, over.json()["code"]) == (413, "too_large")
            assert declared.status_code == 413
            assert (plain.status_code, plain.json()["code"]) == (415, "unsupported_media_type")
            for answer in (extra, number, odd):
                assert (answer.status_code, answer.json()["code"]) == (400, "invalid_request")
            assert ELEVEN_KEY not in extra.text and "<b>" not in odd.text
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_a_missing_or_wrong_secret_keeps_nothing(tmp_path: Path) -> None:
    harness = _harness(choice_settings(tmp_path), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, _ = await joined(http)
            missing = await post(http, "/choices", {"call_id": call_id, "stt": "scribe"})
            wrong = await _choose(http, call_id, "made-up-wrong-secret", stt="scribe")
            assert (missing.status_code, wrong.status_code) == (400, 403)
            assert wrong.json()["code"] == "forbidden"
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_before_the_start_both_routes_answer_not_started(tmp_path: Path) -> None:
    harness = _harness(choice_settings(tmp_path), Built())
    app = harness.app()

    async def scene() -> None:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://t2v.test") as http:
            menu = await http.get(PREFIX + "/choices")
            chosen = await _choose(http, "c-1", "s", stt="scribe")
        assert (menu.status_code, menu.json()["code"]) == (503, "not_started")
        assert (chosen.status_code, chosen.json()["code"]) == (503, "not_started")

    asyncio.run(scene())


def test_the_settings_own_is_kept_as_none_and_a_choice_of_none_drops_one(tmp_path: Path) -> None:
    harness = _harness(choice_settings(tmp_path), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            own = {"stt": "whisper", "model": "gpt-oss-120b", "voice": "orpheus"}
            assert (await _choose(http, call_id, secret, **own)).status_code == 204
            assert _lookup(harness)(call_id) is None
            other, other_secret = await joined(http)
            assert (await _choose(http, other, other_secret, model="gpt-5.5")).status_code == 204
            assert (await _choose(http, other, other_secret)).status_code == 204
            assert _lookup(harness)(other) is None

    asyncio.run(scene())


def test_with_the_setting_off_nothing_is_mounted_and_calls_are_built_as_before(
    tmp_path: Path,
) -> None:
    harness = _harness(choice_settings(tmp_path, on=False), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            menu = await http.get(PREFIX + "/choices")
            chosen = await _choose(http, call_id, secret, stt="scribe")
            assert (menu.status_code, chosen.status_code) == (404, 404)
            assert (await offered(http, call_id, secret)).status_code == 200
            assert harness.runtime.call_choice(call_id) is None

    asyncio.run(scene())
    given = harness.built[-1]
    assert "chosen" not in given and "stt_model" not in given  # today's calls (GP-18)


@pytest.mark.parametrize("field", ["choice", "stt", "model", "voice"])
def test_a_join_or_an_offer_carrying_a_choice_is_refused(field: str, tmp_path: Path) -> None:
    harness = _harness(choice_settings(tmp_path), Built())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            join = await post(http, "/join", {"token": TOKEN, "protocol": 1, field: "scribe"})
            assert (join.status_code, join.json()["code"]) == (400, "invalid_request")
            call_id, secret = await joined(http)
            body = {"call_id": call_id, "sdp": "v=0", "type": "offer", "offer_secret": secret}
            offer = await post(http, "/offer", {**body, field: "scribe"})
            assert (offer.status_code, offer.json()["code"]) == (400, "invalid_request")
            assert _lookup(harness)(call_id) is None

    asyncio.run(scene())


def test_no_answer_and_no_log_line_shows_a_key_a_key_file_or_a_voice_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = _harness(choice_settings(tmp_path), Built())
    answers: dict[str, str] = {}

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answers["menu"] = (await http.get(PREFIX + "/choices")).text
            call_id, secret = await joined(http)
            for name, ids in {
                "kept": {"stt": "scribe", "model": "gpt-5.5", "voice": "bayan"},
                "refused": {"voice": "klingon"},
                "odd": {"voice": "Jasem"},
            }.items():
                answers[name] = (await _choose(http, call_id, secret, **ids)).text
            assert _lookup(harness)(call_id) is not None

    asyncio.run(scene())
    menu = json.loads(answers["menu"])
    assert menu["default"] == {"stt": "whisper", "model": "gpt-oss-120b", "voice": "orpheus"}
    surfaces = {**answers, **shown(caplog=caplog)}
    for value in (GROQ_KEY, ELEVEN_KEY, OPENAI_KEY, TELNYX_KEY, KEY_FILE, *VOICE_IDS):
        assert holding(value, surfaces) == [], value
    assert "call_choice_made" in caplog.text and "call_choice_refused" in caplog.text
