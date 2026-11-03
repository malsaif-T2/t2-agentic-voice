"""Serving a runtime (api/server.py): `serve`'s app with FastAPI's telemetry and docs pages off and
CORS for `server.allowed_origins` alone; uvicorn's settings, its proxy headers trusted only from
`server.forwarded_allow_ips` (an `X-Forwarded-For` from any other peer ignored) and off under
`t2v dev`; the selector event loop; the refusals before uvicorn starts; and
`combine_lifespans`. A real server in a child process: test_serving.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from t2_agentic_voice.api import server
from t2_agentic_voice.api.protocol import OFFER_SECRET_HEADER
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.api.server import (
    TELEMETRY_OFF,
    build_app,
    combine_lifespans,
    serve,
    serve_dev,
    uvicorn_config,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    PREFIX,
    TOKEN,
    Harness,
    dev_settings,
    post,
)

pytestmark = pytest.mark.usefixtures("patched_stores")
ORIGIN = "https://www.example.test"


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[uvicorn.Config]:
    """Each uvicorn config `serve` runs, in place of running it."""
    configs: list[uvicorn.Config] = []
    monkeypatch.setattr(server, "run", configs.append)
    return configs


def _preflight(origin: str) -> dict[str, str]:
    return {
        "origin": origin,
        "access-control-request-method": "POST",
        "access-control-request-headers": f"content-type, {OFFER_SECRET_HEADER}",
    }


def test_serves_app_answers_cors_for_its_listed_origins_alone(tmp_path: Path) -> None:
    settings = dev_settings(tmp_path, server=ServerSettings(allowed_origins=(ORIGIN,)))
    app = build_app(Harness(settings).runtime, prefix=PREFIX)

    async def scene() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t2v.test") as http:
            listed = await http.options(PREFIX + "/offer", headers=_preflight(ORIGIN))
            other = await http.options(
                PREFIX + "/offer", headers=_preflight("https://evil.example.test")
            )
            docs = [(await http.get(path)).status_code for path in ("/docs", "/openapi.json")]
        assert listed.status_code == 200
        assert listed.headers["access-control-allow-origin"] == ORIGIN
        assert {"POST", "PATCH"} <= set(listed.headers["access-control-allow-methods"].split(", "))
        allowed = listed.headers["access-control-allow-headers"].lower()
        assert "content-type" in allowed and OFFER_SECRET_HEADER.lower() in allowed
        assert other.status_code == 400
        assert "access-control-allow-origin" not in other.headers
        for header in ("allow-methods", "allow-headers", "max-age"):
            assert f"access-control-{header}" in other.headers
        assert docs == [404, 404]

    asyncio.run(scene())
    assert app._telemetry["tracing"] is False and app._telemetry["auto_configure"] is False
    assert {k: app._telemetry[k] for k in TELEMETRY_OFF} == TELEMETRY_OFF  # type: ignore[literal-required]


def test_uvicorn_runs_one_quiet_worker_with_no_proxy_headers_by_default(tmp_path: Path) -> None:
    config = uvicorn_config(
        FastAPI(), host="127.0.0.1", port=7860, settings=dev_settings(tmp_path), proxy=True
    )
    assert (config.workers, config.access_log, config.server_header) == (1, False, False)
    assert (config.log_config, config.lifespan) == (None, "on")
    assert (config.proxy_headers, config.forwarded_allow_ips) == (False, [])


@pytest.mark.parametrize(
    ("peer", "proxy", "seen"),
    [
        ("127.0.0.1", True, "127.0.0.1"),  # an untrusted peer's header is ignored
        ("10.0.0.1", True, "203.0.113.9"),  # the trusted proxy's is taken
        ("10.0.0.1", False, "10.0.0.1"),  # t2v dev trusts none
    ],
)
def test_forwarded_for_is_taken_only_from_a_trusted_proxy(
    peer: str, proxy: bool, seen: str, tmp_path: Path
) -> None:
    settings = dev_settings(tmp_path, server=ServerSettings(forwarded_allow_ips=("10.0.0.1",)))
    harness = Harness(settings)
    app = build_app(harness.runtime, prefix=PREFIX)
    config = uvicorn_config(app, host="127.0.0.1", port=7860, settings=settings, proxy=proxy)
    config.load()

    async def scene() -> None:
        transport = httpx.ASGITransport(app=config.loaded_app, client=(peer, 50000))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://t2v.test") as http,
        ):
            answer = await post(
                http, "/join", {"token": TOKEN, "protocol": 1}, **{"x-forwarded-for": "203.0.113.9"}
            )
        assert answer.status_code == 200

    asyncio.run(scene())
    assert harness.identity.asked[0][1].client_host == seen


def test_serve_runs_the_runtime_with_its_settings(
    tmp_path: Path, ran: list[uvicorn.Config]
) -> None:
    harness = Harness(dev_settings(tmp_path))
    serve(lambda: harness.runtime, host="0.0.0.0", port=9000, prefix="/calls")  # noqa: S104
    [config] = ran
    assert (config.host, config.port) == ("0.0.0.0", 9000)  # noqa: S104
    assert asyncio.run(_statuses(config, "/calls/health", "/calls/dev")) == [503, 404]


def test_serve_dev_binds_loopback_with_no_proxy_headers_and_the_dev_page(
    tmp_path: Path, ran: list[uvicorn.Config]
) -> None:
    settings = dev_settings(tmp_path, server=ServerSettings(forwarded_allow_ips=("10.0.0.1",)))
    runtime = VoiceRuntime(AGENT, settings=settings)  # no identity: DevIdentity
    serve_dev(lambda: runtime, port=9001)
    [config] = ran
    assert (config.host, config.port, config.proxy_headers) == ("127.0.0.1", 9001, False)
    assert asyncio.run(_statuses(config, "/voice/dev")) == [503]  # mounted, not started


async def _statuses(config: uvicorn.Config, *paths: str) -> list[int]:
    """The status each path answers on the app `config` serves, its lifespan not run."""
    app: Any = config.app
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://t2v.test") as http:
        return [(await http.get(path)).status_code for path in paths]


@pytest.mark.parametrize("case", ["env test", "no identity"])
def test_serve_refuses_before_uvicorn_starts(
    case: str, settings: VoiceSettings, tmp_path: Path, ran: list[uvicorn.Config]
) -> None:
    given = settings if case == "env test" else dev_settings(tmp_path)
    with pytest.raises(ConfigurationError, match="FIX:"):
        serve(lambda: VoiceRuntime(AGENT, settings=given))
    assert ran == []


class _Server:
    """uvicorn's server, recording the loop it was served on."""

    loops: ClassVar[list[type[asyncio.AbstractEventLoop]]] = []

    def __init__(self, config: uvicorn.Config) -> None:
        self.config = config

    async def serve(self) -> None:
        _Server.loops.append(type(asyncio.get_running_loop()))


def test_uvicorn_runs_on_a_selector_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uvicorn, "Server", _Server)
    server.run(
        uvicorn_config(
            FastAPI(), host="127.0.0.1", port=1, settings=dev_settings(tmp_path), proxy=False
        )
    )
    assert _Server.loops == [asyncio.SelectorEventLoop]


def _lifespan(name: str, log: list[str], *, fails: bool = False) -> Any:
    @asynccontextmanager
    async def lifespan(app: object) -> AsyncIterator[None]:
        if fails:
            raise RuntimeError(name)
        log.append(f"enter {name}")
        try:
            yield
        finally:
            log.append(f"leave {name}")

    return lifespan


def test_combined_lifespans_enter_in_order_and_leave_in_reverse() -> None:
    log: list[str] = []
    combined = combine_lifespans(_lifespan("a", log), _lifespan("b", log))

    async def scene() -> None:
        async with combined(object()):
            log.append("serving")

    asyncio.run(scene())
    assert log == ["enter a", "enter b", "serving", "leave b", "leave a"]


def test_combined_lifespans_leave_those_entered_when_a_later_one_fails() -> None:
    log: list[str] = []
    combined = combine_lifespans(_lifespan("a", log), _lifespan("b", log, fails=True))

    async def scene() -> None:
        with pytest.raises(RuntimeError, match="b"):
            async with combined(object()):
                log.append("serving")

    asyncio.run(scene())
    assert log == ["enter a", "leave a"]
