"""The test console's token (api/dev_console.py, D-083): `POST <prefix>/dev/token` mints a signed
join token for the caller the app declares (`server.dev_caller`), never for one the request
names, with the server's consent version and the console's keep-audio box (off unless the body
says true); the runtime's own identity source verifies it once, as it does a widget's token. The
route answers only under the console's guard (`env` dev, the dev page, a loopback client, a
loopback `Host`), and gives the plain 404 when the app declares no dev caller or the server holds
no join key that signs, so the page joins with `dev` instead. Nothing it mints reaches a log."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from t2_agentic_voice.api import dev_console
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.config import Environment, VoiceSettings
from t2_agentic_voice.core.identity import Caller, allows_recording
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.privacy import PrivacySettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext
from t2_agentic_voice.identity import SignedJoinTokens
from t2_agentic_voice.stores import MemoryUsedTokens
from t2_agentic_voice.voice.calls import Calls

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    OFFER_SDP,
    PREFIX,
    TOKEN,
    FakeIdentity,
)
from tests.t2_agentic_voice.fakes import FakeCalls, FakeClock, FakeSpeechToText, FakeTextToSpeech

pytestmark = pytest.mark.usefixtures("patched_stores")

KEY = "a-made-up-join-key-of-forty-bytes-0123456"
VERSION = "console-test-1"
DEV_CALLER = Caller(subject="demo-owner", attributes={"customer_email": "demo@example.com"})
OTHER = {"subject": "someone-else", "attributes": {"customer_email": "other@example.com"}}
LOCAL = "http://127.0.0.1:7860"
STATIC = Path(dev_console.__file__).parent / "static"


def _settings(
    tmp_path: Path,
    *,
    env: Environment = "dev",
    dev_page: bool = True,
    caller: Caller | None = DEV_CALLER,
    keys: bool = True,
    signs: bool = True,
) -> VoiceSettings:
    join = JoinSettings(
        keys={"k1": SecretStr(KEY)} if keys else {},
        current_kid="k1" if keys and signs else None,
    )
    return VoiceSettings(
        env=env,
        storage=StorageSettings(var_dir=tmp_path / "var"),
        server=ServerSettings(dev_page=dev_page, dev_caller=caller),
        join=join,
        privacy=PrivacySettings(consent_version=VERSION),
    )


def _app(
    settings: VoiceSettings, identity: IdentityVerifier | None = None
) -> tuple[FastAPI, FakeCalls]:
    """The runtime's router under PREFIX, its callers verified by `identity` (the signed tokens
    the settings describe unless given), its calls the fake's."""
    calls = FakeCalls()

    def built(**given: Any) -> Calls:
        return calls

    runtime = VoiceRuntime(
        AGENT,
        settings=settings,
        identity=identity or SignedJoinTokens.from_settings(settings.join),
        providers=Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech()),
        _calls=built,
        _clock=FakeClock(),
    )
    app = FastAPI()
    app.include_router(runtime.router(), prefix=PREFIX)
    return app, calls


@asynccontextmanager
async def _serving(
    app: FastAPI, *, peer: str = "127.0.0.1", base: str = LOCAL
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=(peer, 50000))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url=base) as http,
    ):
        yield http


async def _post(http: httpx.AsyncClient, path: str, body: object) -> httpx.Response:
    text = body if isinstance(body, str) else json.dumps(body)
    headers = {"content-type": "application/json"}
    return await http.post(PREFIX + path, content=text, headers=headers)


def _minted(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [vars(r)["fields"] for r in caplog.records if r.getMessage() == "dev_token_minted"]


@pytest.mark.parametrize(
    ("body", "keep"),
    [({}, False), ({"record_audio": False}, False), ({"record_audio": True}, True)],
)
def test_the_console_mints_for_the_apps_dev_caller_and_the_call_joins_with_it_once(
    body: dict[str, object], keep: bool, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    app, calls = _app(settings)

    async def scene() -> None:
        async with _serving(app) as http:
            answer = await _post(http, "/dev/token", body)
            assert answer.status_code == 200, answer.text
            assert answer.headers["cache-control"] == "no-store"
            assert set(answer.json()) == {"token"}
            token = answer.json()["token"]
            joined = await _post(http, "/join", {"token": token, "protocol": 1})
            assert joined.status_code == 200, joined.text
            call = joined.json()
            offer = {"call_id": call["call_id"], "sdp": OFFER_SDP, "type": "offer"}
            offered = await _post(http, "/offer", {**offer, "offer_secret": call["offer_secret"]})
            assert offered.status_code == 200, offered.text
            again = await _post(http, "/join", {"token": token, "protocol": 1})
            assert (again.status_code, again.json()["code"]) == (403, "join_rejected")

    asyncio.run(scene())
    [(_, caller, consent, _)] = calls.offers.values()
    assert caller == DEV_CALLER  # the app's caller, as a widget's token carries it
    assert (consent.version, consent.record_audio) == (VERSION, keep)
    assert allows_recording(consent) is keep  # a signed consent, as a widget's


def test_the_token_verifies_with_the_signed_tokens_the_join_settings_describe(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    app, _ = _app(settings)

    async def scene() -> str:
        async with _serving(app) as http:
            answer = await _post(http, "/dev/token", {"record_audio": False})
        token: str = answer.json()["token"]
        return token

    token = asyncio.run(scene())
    join = JoinContext(env="dev", client_host="127.0.0.1", used_tokens=MemoryUsedTokens())
    tokens = SignedJoinTokens.from_settings(settings.join)
    caller, consent = asyncio.run(tokens.verify(token, join=join))
    assert (caller.subject, dict(caller.attributes)) == ("demo-owner", dict(DEV_CALLER.attributes))
    assert (consent.version, consent.record_audio) == (VERSION, False)


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        (OTHER, 400, "invalid_request"),
        ({"caller": OTHER}, 400, "invalid_request"),
        ({"record_audio": False, "attributes": OTHER["attributes"]}, 400, "invalid_request"),
        ({"record_audio": False, "sub": "someone-else"}, 400, "invalid_request"),
        ({"record_audio": False, "attrs": OTHER["attributes"]}, 400, "invalid_request"),
        ({"record_audio": "true"}, 400, "invalid_request"),
        ({"record_audio": 1}, 400, "invalid_request"),
        ([], 400, "invalid_request"),
        ("not json", 400, "invalid_request"),
        ({"record_audio": False, "pad": "x" * 4096}, 413, "too_large"),
    ],
)
def test_a_body_that_names_a_caller_or_is_not_the_boxs_choice_is_refused(
    body: object, status: int, code: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    app, _ = _app(_settings(tmp_path))

    async def scene() -> httpx.Response:
        async with _serving(app) as http:
            return await _post(http, "/dev/token", body)

    answer = asyncio.run(scene())
    assert (answer.status_code, answer.json()["code"]) == (status, code)
    assert "token" not in answer.json()
    assert _minted(caplog) == []


def test_a_body_not_sent_as_json_is_refused_before_it_is_read(tmp_path: Path) -> None:
    app, _ = _app(_settings(tmp_path))

    async def scene() -> httpx.Response:
        async with _serving(app) as http:
            return await http.post(PREFIX + "/dev/token", content="{}")

    answer = asyncio.run(scene())
    assert (answer.status_code, answer.json()["code"]) == (415, "unsupported_media_type")


@pytest.mark.parametrize(
    ("peer", "base", "env", "dev_page"),
    [
        ("192.0.2.7", LOCAL, "dev", True),  # not this machine
        ("127.0.0.1", "http://t2v.test", "dev", True),  # a name pointed at this machine
        ("127.0.0.1", LOCAL, "dev", False),  # no dev page: not mounted
        ("127.0.0.1", LOCAL, "staging", False),  # another env: never mounted
        ("127.0.0.1", LOCAL, "prod", False),
    ],
)
def test_the_token_answers_this_machine_by_a_loopback_name_under_dev_alone(
    peer: str, base: str, env: Environment, dev_page: bool, tmp_path: Path
) -> None:
    app, _ = _app(_settings(tmp_path, env=env, dev_page=dev_page))

    async def scene() -> httpx.Response:
        async with _serving(app, peer=peer, base=base) as http:
            return await _post(http, "/dev/token", {"record_audio": False})

    answer = asyncio.run(scene())
    assert (answer.status_code, answer.json()) == (404, {"detail": "Not Found"})


@pytest.mark.parametrize(
    ("given", "reason"),
    [
        ({"caller": None}, "no_dev_caller"),
        ({"keys": False}, "no_join_key"),
        ({"signs": False}, "no_join_key"),
    ],
)
def test_with_no_dev_caller_or_no_key_that_signs_it_refuses_and_the_page_joins_as_dev(
    given: dict[str, Any], reason: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    identity = FakeIdentity()
    app, _ = _app(_settings(tmp_path, **given), identity)

    async def scene() -> tuple[httpx.Response, httpx.Response]:
        async with _serving(app) as http:
            refused = await _post(http, "/dev/token", {"record_audio": False})
            joined = await _post(http, "/join", {"token": "dev", "protocol": 1})
        return refused, joined

    refused, joined = asyncio.run(scene())
    assert (refused.status_code, refused.json()) == (404, {"detail": "Not Found"})
    assert joined.status_code == 200  # `t2v dev` as before: the page's `dev`
    lines = [vars(r)["fields"] for r in caplog.records if r.getMessage() == "dev_token_refused"]
    assert lines == [{"reason": reason}]
    assert _minted(caplog) == []


def test_nothing_it_mints_is_logged_and_its_line_holds_the_choice_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    app, _ = _app(_settings(tmp_path))

    async def scene() -> str:
        async with _serving(app) as http:
            answer = await _post(http, "/dev/token", {"record_audio": True})
            token: str = answer.json()["token"]
            await _post(http, "/join", {"token": token, "protocol": 1})
        return token

    token = asyncio.run(scene())
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert holding(token, surfaces) == []
    assert holding(KEY, surfaces) == []
    assert holding(token.rpartition(".")[2], surfaces) == []  # its signature, alone
    assert _minted(caplog) == [{"record_audio": True}]


def test_a_typed_token_still_joins_as_before(tmp_path: Path) -> None:
    identity = FakeIdentity()
    app, _ = _app(_settings(tmp_path), identity)

    async def scene() -> httpx.Response:
        async with _serving(app) as http:
            return await _post(http, "/join", {"token": TOKEN, "protocol": 1})

    assert asyncio.run(scene()).status_code == 200
    assert [token for token, _ in identity.asked] == [TOKEN]


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, tuple[str, dict[str, str | None]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if found.get("id"):
            self.tags[str(found["id"])] = (tag, found)


def test_the_page_leaves_the_token_empty_and_its_audio_box_off() -> None:
    page = _Tags()
    page.feed((STATIC / dev_console.PAGE).read_text(encoding="utf-8"))
    tag, token = page.tags["token"]
    assert tag == "input" and token.get("value") in (None, "")
    assert "console makes one" in (token.get("placeholder") or "")
    tag, keep = page.tags["keep-audio"]
    assert (tag, keep.get("type")) == ("input", "checkbox")
    assert "checked" not in keep  # off unless ticked


def test_the_pages_start_asks_for_a_token_when_the_field_is_empty_and_falls_back_to_dev() -> None:
    script = (STATIC / dev_console.SCRIPT).read_text(encoding="utf-8")
    assert re.search(r'fetch\("token",\s*\{\s*method: "POST"', script)
    assert 'record_audio: $("keep-audio").checked' in script
    assert '"content-type": "application/json"' in script
    assert 'token: $("token").value || "dev"' not in script  # the old Start
    start = script.index("async function start()")
    # The client asks for it once the microphone is open, as the widget's getToken is asked.
    assert "getToken: async () =>" in script[start:] and "await joinToken()" in script[start:]
    assert "token: joining.token" not in script[start:]
    helper = script[script.index("async function joinToken()") : start]
    assert 'const typed = $("token").value;' in helper and "if (typed)" in helper  # as typed
    assert 'return { token: "dev"' in helper  # no token minted: the dev caller's
