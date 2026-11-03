"""The router's other routes (api/runtime.py, "The router"; the design's 4.5 and 10.5): every
route answers 503 `not_started` while the lifespan has not run, `/health`, `/ready`, the client
script and `/dev` included (the decision log, 2026-11-03); `/health` holds what is built and no
path; the browser's files from the static folder with their headers; and `/dev` only with `env`
dev and the dev page on, to loopback clients, `env` checked before the client's address is
read."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException, Request
from t2_agentic_voice.api import router as routing
from t2_agentic_voice.api.offers import CallRecords
from t2_agentic_voice.api.router import Served, _Routes, loopback
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    END,
    OFFER_SDP,
    PREFIX,
    TOKEN,
    FakeIdentity,
    Harness,
    client,
    dev_settings,
    patch,
    post,
    refused,
    serving,
)
from tests.t2_agentic_voice.fakes import FakeCalls, FakeClock

pytestmark = pytest.mark.usefixtures("patched_stores")

SCRIPT = b"export class VoiceClient {}\n"
PAGE = b"<!doctype html><title>dev</title>\n"


@pytest.fixture
def static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A static folder of the test's own, which the router reads the browser's files from."""
    folder = tmp_path / "static"
    folder.mkdir()
    (folder / routing.CLIENT_SCRIPT).write_bytes(SCRIPT)
    (folder / routing.DEV_PAGE).write_bytes(PAGE)
    monkeypatch.setattr(routing, "STATIC", folder)
    return folder


# Every route, with a body its route takes.
REQUESTS: list[tuple[str, str, dict[str, object] | None]] = [
    ("POST", "/join", {"token": TOKEN, "protocol": 1}),
    ("POST", "/offer", {"call_id": "c-1", "sdp": OFFER_SDP, "type": "offer"}),
    ("PATCH", "/offer", {"call_id": "c-1", "candidates": [END]}),
    ("GET", "/health", None),
    ("GET", "/ready", None),
    ("GET", "/client/1/t2v-client.js", None),
    ("GET", "/dev", None),
]


@pytest.mark.parametrize(("method", "path", "body"), REQUESTS)
def test_every_route_answers_not_started_outside_the_lifespan(
    method: str, path: str, body: dict[str, object] | None, tmp_path: Path, static: Path
) -> None:
    harness = Harness(dev_settings(tmp_path))
    app = harness.app(dev=True)

    async def ask() -> None:
        async with client(app) as http:
            answer = await http.request(method, PREFIX + path, json=body)
        assert answer.status_code == 503
        assert answer.json()["code"] == "not_started"
        if body is not None:
            refused(answer, f"{method} {path}", "not_started")

    asyncio.run(ask())  # before the lifespan

    async def after() -> None:
        async with serving(app):
            pass
        await ask()

    asyncio.run(after())  # and after it
    assert harness.identity.asked == []


def test_health_and_ready_hold_only_what_is_built(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            health = await http.get(PREFIX + "/health")
            ready = await http.get(PREFIX + "/ready")
        assert health.json() == {"env": "dev", "calls": 0}
        assert str(tmp_path) not in health.text
        assert ready.json() == {"ready": True}

    asyncio.run(scene())


class _Broken(FakeCalls):
    def phase(self, call_id: str) -> None:
        raise RuntimeError("phase failed")


def test_a_crash_is_a_500_in_the_one_shape(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path), calls=_Broken())

    async def scene() -> None:
        async with serving(harness.app()) as http:
            joined = (await post(http, "/join", {"token": TOKEN, "protocol": 1})).json()
            body = {"call_id": joined["call_id"], "sdp": OFFER_SDP, "type": "offer"}
            secret = {"offer_secret": joined["offer_secret"]}
            await post(http, "/offer", {**body, **secret})
            health = await http.get(PREFIX + "/health")
            patched = await patch(
                http, {"call_id": joined["call_id"], "candidates": [END], **secret}
            )
        assert (health.status_code, health.json()["code"]) == (500, "internal_error")
        assert patched.status_code == 500
        refused(patched, "PATCH /offer", "internal_error")

    asyncio.run(scene())


def test_the_client_script_is_served_from_the_static_folder(tmp_path: Path, static: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            first = await http.get(PREFIX + "/client/1/t2v-client.js")
            (static / routing.CLIENT_SCRIPT).unlink()
            kept = await http.get(PREFIX + "/client/1/t2v-client.js")
        assert first.content == SCRIPT == kept.content
        assert first.headers["content-type"] == "text/javascript; charset=utf-8"
        assert first.headers["x-content-type-options"] == "nosniff"

    asyncio.run(scene())


def test_a_missing_browser_file_is_the_plain_404(tmp_path: Path, static: Path) -> None:
    (static / routing.CLIENT_SCRIPT).unlink()
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answer = await http.get(PREFIX + "/client/1/t2v-client.js")
        assert (answer.status_code, answer.json()) == (404, {"detail": "Not Found"})

    asyncio.run(scene())


@pytest.mark.parametrize(
    ("dev", "dev_page", "peer", "served"),
    [
        (True, False, "127.0.0.1", True),  # t2v dev
        (False, True, "127.0.0.1", True),  # server.dev_page
        (False, True, "::1", True),
        (False, True, "192.0.2.7", False),  # not loopback
        (False, False, "127.0.0.1", False),  # not mounted
    ],
)
def test_the_dev_page_serves_loopback_clients_in_dev(
    dev: bool, dev_page: bool, peer: str, served: bool, tmp_path: Path, static: Path
) -> None:
    settings = dev_settings(tmp_path, server=ServerSettings(dev_page=dev_page))
    harness = Harness(settings)

    async def scene() -> None:
        async with serving(harness.app(dev=dev), peer=(peer, 50000)) as http:
            answer = await http.get(PREFIX + "/dev")
        if not served:
            assert (answer.status_code, answer.json()) == (404, {"detail": "Not Found"})
            return
        assert answer.content == PAGE
        assert answer.headers["content-security-policy"] == (
            "default-src 'none'; script-src 'self'; connect-src 'self'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        assert answer.headers["x-content-type-options"] == "nosniff"
        assert answer.headers["referrer-policy"] == "no-referrer"
        assert answer.headers["permissions-policy"] == "microphone=(self)"
        assert answer.headers["cache-control"] == "no-store"
        assert answer.headers["content-type"] == "text/html; charset=utf-8"

    asyncio.run(scene())


class _NoAddress:
    """A request whose client's address must not be read."""

    @property
    def client(self) -> object:
        raise AssertionError("the client's address was read")


@pytest.mark.parametrize("env", ["test", "staging", "prod"])
def test_the_dev_page_refuses_any_env_but_dev_before_it_reads_the_address(
    env: str, tmp_path: Path
) -> None:
    settings = VoiceSettings(env=env)  # type: ignore[arg-type]
    served = Served(
        agent=AGENT,
        settings=settings,
        identity=FakeIdentity(),
        records=CallRecords(window_s=1.0),
        clock=FakeClock(),
        running=lambda: None,
        dev_page=True,
    )
    with pytest.raises(HTTPException) as raised:
        asyncio.run(_Routes(served).dev(cast(Request, _NoAddress()), "ref-12345678"))
    assert raised.value.status_code == 404


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("127.0.0.1", True),
        ("127.8.9.1", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("::ffff:10.0.0.1", False),
        ("10.0.0.1", False),
        ("fe80::1%eth0", False),
        ("testclient", False),
        ("", False),
        (None, False),
    ],
)
def test_loopback_is_this_machine_alone(host: str | None, local: bool) -> None:
    assert loopback(host) is local
