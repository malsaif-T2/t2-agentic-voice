"""The flight agent's server (flight_voice/server.py): the page's files with the library's page
headers, the token route minting for the demo traveler alone whatever the request says, its
tokens a day the setting's, the library's router under `/voice`, uvicorn configured as the mount
needs, and `make_app` building the talker over the mock airline the settings set, each call's
trip dropped as the call ends; the command refusing settings it cannot run with. The library's
runtime has its own tests: these give the app a router of their own, or fake the runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
import uvicorn
from fastapi import APIRouter
from fastapi.testclient import TestClient
from flight_voice import server
from flight_voice.agent import NAME
from flight_voice.server import FILES, HOST, PORT, VOICE_PREFIX, WEB, airline_of, server_config
from flight_voice.settings import load
from flight_voice.traveler import TRAVELER_ID, demo_caller
from t2_agentic_voice import Caller, VoiceSettings
from t2_agentic_voice.events import CallEnded
from t2_agentic_voice.server import page_headers

from tests.flight_voice.server_support import (
    CODE,
    LOCAL,
    LOOPBACK,
    Minter,
    app,
    settings,
)

ORIGIN = "https://www.example.com"
CONSENT = {"version": None, "record_audio": False}


def _client(folder: Path, **given: Any) -> TestClient:
    return TestClient(app(folder, **given), client=LOOPBACK, base_url=LOCAL)


def test_every_page_file_is_served_with_the_page_headers(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for path, (name, media_type) in FILES.items():
        answer = client.get(path)
        assert answer.status_code == 200, path
        assert answer.text == name
        assert answer.headers["content-type"] == media_type
        for header, value in page_headers(None).items():
            assert answer.headers[header] == value
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_only_the_website_set_may_frame_the_page(tmp_path: Path) -> None:
    client = _client(tmp_path, website_origin=ORIGIN)
    policy = client.get("/").headers["content-security-policy"]
    assert f"frame-ancestors {ORIGIN}" in policy
    assert "script-src 'self'" in policy and "'unsafe-inline'" not in policy


def test_the_token_names_the_demo_traveler_whatever_the_request_says(tmp_path: Path) -> None:
    minter = Minter()
    client = _client(tmp_path, minter=minter)
    answer = client.post("/token", json={"code": CODE, "consent": CONSENT})
    assert answer.status_code == 200
    assert answer.json() == {"token": "made-up-token"}
    for sneaked in (
        {"caller": {"subject": "other", "attributes": {TRAVELER_ID: "T-0002"}}},
        {"traveler_id": "T-0002"},
        {"attributes": {TRAVELER_ID: "T-0002"}},
    ):
        refused = client.post("/token", json={"code": CODE, "consent": CONSENT, **sneaked})
        assert refused.status_code == 400
    assert [caller for caller, _ in minter.minted] == [demo_caller()]
    assert minter.minted[0][0].attributes[TRAVELER_ID] == "T-0001"


def test_a_wrong_code_mints_nothing(tmp_path: Path) -> None:
    minter = Minter()
    client = _client(tmp_path, minter=minter)
    answer = client.post("/token", json={"code": "not-the-code-at-all-0123", "consent": CONSENT})
    assert answer.status_code == 403
    assert minter.minted == []


def test_the_tokens_a_day_are_the_settings(tmp_path: Path) -> None:
    client = _client(tmp_path, tokens_per_day=2)
    answers = [
        client.post("/token", json={"code": CODE, "consent": CONSENT}).status_code for _ in range(3)
    ]
    assert answers == [200, 200, 429]


def test_the_librarys_router_is_served_under_its_prefix(tmp_path: Path) -> None:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    built = server.build_app(
        settings(),
        router=router,
        minter=Minter(),
        airline=airline_of(settings().app),
        web=tmp_path,
    )
    client = TestClient(built, client=LOOPBACK, base_url=LOCAL)
    assert client.get(f"{VOICE_PREFIX}/health").json() == {"ok": True}
    assert VOICE_PREFIX == "/voice"


def test_uvicorn_runs_as_the_server_needs(tmp_path: Path) -> None:
    config = server_config(app(tmp_path), VoiceSettings(env="dev"), host=HOST, port=PORT)
    assert (config.host, config.port, config.workers) == ("127.0.0.1", 7862, 1)
    assert config.proxy_headers is False
    assert config.access_log is False
    assert config.server_header is False
    assert config.loop == "asyncio:SelectorEventLoop"


def test_the_airline_is_the_settings() -> None:
    built = airline_of(
        settings(
            today="2026-11-16",
            search_mode="slow",
            slow_s=2,
            booking_mode="refuse",
            airline_code="NJ",
        ).app
    )
    assert str(built.today()) == "2026-11-16"
    assert (built.search_mode, built.slow_s, built.code) == ("slow", 2, "NJ")
    assert (built.bookings.mode, built.bookings.can_find) == ("refuse", True)


class _Runtime:
    """A runtime that keeps what it was built with and the observers it was given."""

    built: ClassVar[list[_Runtime]] = []

    def __init__(self, agent: Any, *, settings: VoiceSettings, identity: Any) -> None:
        self.agent, self.settings, self.identity = agent, settings, identity
        self.observers: list[tuple[type, Any]] = []
        _Runtime.built.append(self)

    def on(self, kind: type) -> Any:
        def register(observer: Any) -> Any:
            self.observers.append((kind, observer))
            return observer

        return register

    def router(self) -> APIRouter:
        return APIRouter()


def test_make_app_serves_the_talker_and_drops_each_calls_trip_as_it_ends(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setattr(server, "VoiceRuntime", _Runtime)
    environment.setenv("FLIGHT_VOICE_PERSONA_NAME_EN", "Fahad")
    loaded = load()
    server.make_app(loaded)
    runtime = _Runtime.built[-1]
    assert runtime.agent.name == NAME
    assert "Fahad" in runtime.agent.languages[1].greeting
    assert runtime.settings is loaded.voice
    ((kind, observer),) = runtime.observers
    assert kind is CallEnded
    assert observer.__name__ == "call_ended"


def test_the_command_refuses_settings_it_cannot_run_with(
    environment: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    environment.setenv("FLIGHT_VOICE_ACCESS_CODE", "short")
    assert server.main([]) == 2
    assert "short" not in capsys.readouterr().out


def test_the_command_serves_the_app_it_makes(environment: pytest.MonkeyPatch) -> None:
    environment.setattr(server, "VoiceRuntime", _Runtime)
    environment.setattr(uvicorn, "Server", _Served)
    assert server.main(["--port", "7999"]) == 0
    assert _Served.ran[-1].port == 7999


class _Served:
    """A server that keeps the configuration it ran with, and runs nothing."""

    ran: ClassVar[list[uvicorn.Config]] = []

    def __init__(self, config: uvicorn.Config) -> None:
        self.config = config

    def run(self) -> None:
        _Served.ran.append(self.config)


def test_the_page_folder_sits_beside_the_apps_source() -> None:
    assert WEB.parent.name == "flight-voice-agent"
    assert Caller(subject="owner", attributes={TRAVELER_ID: "T-0001"}) == demo_caller()
