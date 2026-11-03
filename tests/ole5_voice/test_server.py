"""The Ole5 app's server (ole5_voice/server.py): the widget's files with its page's headers, the
token route and the library's router in one app with FastAPI's telemetry off and the app's own
CORS, and uvicorn trusting proxy headers only from `server.forwarded_allow_ips`. The library's
runtime is Track F's: these tests give the app a router of their own, and `make_app` fakes of
the runtime and the signed tokens."""

from __future__ import annotations

import asyncio
import json
import re
import runpy
import subprocess
import sys
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

import pytest
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from ole5_voice import server
from ole5_voice.server import (
    AGENT,
    FILES,
    OFFER_SECRET_HEADER,
    PORT,
    VOICE_PREFIX,
    WEB,
    build_app,
    page_headers,
    server_config,
)
from ole5_voice.settings import AppSettings, Settings
from pydantic import SecretStr
from t2_agentic_voice import Caller, Consent, JoinSettings, ServerSettings, VoiceSettings
from t2_agentic_voice.api import protocol

from tests.isolation import child_shell
from tests.leaks import holding, shown

CODE = "made-up-access-code-0123"
WRONG = "not-the-code-at-all-0123"
ORIGIN = "https://www.example.com"
BODY = {"code": WRONG, "consent": {"version": None, "record_audio": False}}


class Minter:
    def __init__(self) -> None:
        self.minted: list[tuple[Caller, Consent]] = []

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        self.minted.append((caller, consent))
        return "made-up-token"


def settings(origin: str | None = None, **server_settings: object) -> Settings:
    app = AppSettings(access_code=SecretStr(CODE), website_origin=origin)
    voice = VoiceSettings(env="dev", server=ServerSettings.model_validate(server_settings))
    return Settings(app=app, voice=voice)


def voice_router() -> APIRouter:
    """A router in place of the library's, with one route of its own."""
    router = APIRouter()
    router.add_api_route("/health", lambda: {"status": "made up"}, methods=["GET"])
    return router


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app(settings(), router=voice_router(), minter=Minter())) as test:
        yield test


def test_the_widget_page_is_served_with_its_headers(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert page.headers["content-security-policy"] == (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["permissions-policy"] == "microphone=(self)"
    assert page.text == (WEB / "index.html").read_text(encoding="utf-8")
    for path, (name, media_type) in FILES.items():
        served = client.get(path)
        assert served.headers["content-type"] == media_type
        assert served.headers["x-content-type-options"] == "nosniff"
        assert served.content == (WEB / name).read_bytes()
    assert client.get("/index.html").status_code == 404
    assert client.get("/web/widget.js").status_code == 404


def test_only_the_website_set_may_frame_the_page() -> None:
    assert page_headers(None)["Content-Security-Policy"].endswith("frame-ancestors 'none'")
    framed = build_app(settings(ORIGIN), router=voice_router(), minter=Minter())
    policy = TestClient(framed).get("/").headers["content-security-policy"]
    assert policy.endswith(f"frame-ancestors {ORIGIN}")
    assert policy.count("frame-ancestors") == 1


class _Page(HTMLParser):
    """The tags of a page, with their attributes, and the text inside its script elements."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.inline: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        self._in = tag

    def handle_data(self, data: str) -> None:
        if self._in in ("script", "style") and data.strip():
            self.inline.append(data)

    def handle_endtag(self, tag: str) -> None:
        self._in = None


def test_the_page_holds_no_inline_script_or_style() -> None:
    """What `script-src 'self'` and `style-src 'self'` need: every script and style from a
    file of the widget's own, and no handler or style attribute."""
    page = _Page()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    assert page.inline == []
    scripts = [attrs for tag, attrs in page.tags if tag == "script"]
    assert scripts == [{"type": "module", "src": "widget.js"}]
    assert all(not name.startswith("on") and name != "style" for _, a in page.tags for name in a)
    assert ("link", {"rel": "stylesheet", "href": "widget.css"}) in page.tags


def test_the_widget_holds_its_consent_labels_and_reaches_the_router() -> None:
    script = (WEB / "widget.js").read_text(encoding="utf-8")
    assert 'export const CONSENT_VERSION = "m2-owner-test-1";' in script
    assert 'stop: "إيقاف"' in script  # the labels Q6 settled
    assert 'agree: "أوافق"' in script
    assert f'from ".{VOICE_PREFIX}/client/1/t2v-client.js"' in script
    assert 'base: "voice"' in script and VOICE_PREFIX == "/voice"
    assert 'fetch("token"' in script
    page = _Page()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    ids = {attrs["id"] for _, attrs in page.tags if attrs.get("id")}
    read = set(re.findall(r'\$\("([a-z-]+)"\)', script))
    assert read and read <= ids


def test_the_token_route_and_the_librarys_router_are_served(client: TestClient) -> None:
    assert client.get(f"{VOICE_PREFIX}/health").json() == {"status": "made up"}
    refused = client.post("/token", json=BODY)
    assert (refused.status_code, refused.json()["code"]) == (403, "wrong_code")
    assert client.get("/openapi.json").status_code == 404


def test_cors_answers_the_allowed_origins_alone() -> None:
    app = build_app(settings(allowed_origins=(ORIGIN,)), router=voice_router(), minter=Minter())
    preflight = {
        "access-control-request-method": "POST",
        "access-control-request-headers": f"content-type, {OFFER_SECRET_HEADER}",
    }
    with TestClient(app) as test:
        allowed = test.options("/voice/offer", headers={"origin": ORIGIN, **preflight})
        other = test.options(
            "/voice/offer", headers={"origin": "https://elsewhere.example", **preflight}
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert set(allowed.headers["access-control-allow-methods"].split(", ")) == {"POST", "PATCH"}
    assert other.status_code == 400
    assert "access-control-allow-origin" not in other.headers
    assert OFFER_SECRET_HEADER == protocol.OFFER_SECRET_HEADER


def test_uvicorn_runs_as_the_server_needs() -> None:
    config = server_config(
        build_app(settings(), router=voice_router(), minter=Minter()),
        settings().voice,
        host="127.0.0.1",
        port=PORT,
    )
    assert (config.host, config.port, config.workers) == ("127.0.0.1", 7861, 1)
    assert config.proxy_headers is False
    assert config.forwarded_allow_ips == []
    assert (config.access_log, config.server_header, config.log_config) == (False, False, None)
    assert config.lifespan == "on"
    assert config.get_loop_factory() is asyncio.SelectorEventLoop
    trusting = server_config(
        FastAPI(), settings(forwarded_allow_ips=("127.0.0.1",)).voice, host="h", port=1
    )
    assert (trusting.proxy_headers, trusting.forwarded_allow_ips) == (True, ["127.0.0.1"])


def _served(trusted: tuple[str, ...]) -> uvicorn.Config:
    loaded = settings(forwarded_allow_ips=trusted)
    config = server_config(
        build_app(loaded, router=voice_router(), minter=Minter()),
        loaded.voice,
        host="127.0.0.1",
        port=PORT,
    )
    config.load()
    return config


def _try(config: uvicorn.Config, peer: str, forwarded: str) -> int:
    test = TestClient(config.loaded_app, client=(peer, 50000))
    return test.post("/token", json=BODY, headers={"x-forwarded-for": forwarded}).status_code


def test_a_forwarded_address_counts_only_from_a_trusted_proxy() -> None:
    """The token route slows an address's second wrong code: whose address it counted shows
    whether uvicorn took the client's X-Forwarded-For."""
    untrusting = _served(())
    assert _try(untrusting, "127.0.0.1", "198.51.100.1") == 403
    assert _try(untrusting, "127.0.0.1", "198.51.100.2") == 429  # the peer's address both times
    trusting = _served(("127.0.0.1",))
    assert _try(trusting, "127.0.0.1", "198.51.100.1") == 403
    assert _try(trusting, "127.0.0.1", "198.51.100.2") == 403  # each its forwarded address
    assert _try(trusting, "127.0.0.1", "198.51.100.1") == 429
    assert _try(trusting, "203.0.113.9", "198.51.100.3") == 403  # an untrusted peer: its own
    assert _try(trusting, "203.0.113.9", "198.51.100.4") == 429


class _Tokens(Minter):
    """Stands in for `SignedJoinTokens`, keeping the settings it was built from."""

    def __init__(self, join: JoinSettings, prefix: str) -> None:
        super().__init__()
        self.built_from = (join, prefix)

    @classmethod
    def from_settings(cls, join: JoinSettings, *, prefix: str) -> _Tokens:
        return cls(join, prefix)


class _Runtime:
    """Stands in for `VoiceRuntime`, keeping what it was given."""

    made: ClassVar[list[_Runtime]] = []

    def __init__(self, agent: object, *, settings: VoiceSettings, identity: object) -> None:
        self.given = (agent, settings, identity)
        _Runtime.made.append(self)

    def router(self) -> APIRouter:
        return voice_router()


def test_the_app_verifies_its_callers_with_the_tokens_it_mints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server, "SignedJoinTokens", _Tokens)
    monkeypatch.setattr(server, "VoiceRuntime", _Runtime)
    _Runtime.made.clear()
    loaded = settings()
    app = server.make_app(loaded)
    [runtime] = _Runtime.made
    agent, voice, identity = runtime.given
    assert (agent, voice) == (AGENT, loaded.voice)
    assert isinstance(identity, _Tokens)
    assert identity.built_from == (loaded.voice.join, "T2V_")
    with TestClient(app) as test:
        assert test.get("/voice/health").status_code == 200
        body = {"code": CODE, "consent": {"version": "v1", "record_audio": True}}
        assert test.post("/token", json=body).json() == {"token": "made-up-token"}
    assert identity.minted == [(Caller(subject="owner"), Consent(version="v1", record_audio=True))]


def test_ole5s_agent_speaks_saudi_arabic_first_and_says_its_name() -> None:
    assert AGENT.name == "ole5"
    assert [language.tag for language in AGENT.languages] == ["ar-SA", "en"]
    assert dict(AGENT.pronounce["Ole5"]) == {"ar": "أُولِي فايف", "en": "Oh-lee five"}
    assert all("Ole5" in language.greeting for language in AGENT.languages)


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_JOIN__KEYS", '{"k1": "a-made-up-join-key-of-forty-bytes-0123456"}')
    monkeypatch.setenv("T2V_JOIN__CURRENT_KID", "k1")
    monkeypatch.setenv("OLE5_VOICE_ACCESS_CODE", CODE)
    return monkeypatch


def test_the_command_serves_the_app(environment: pytest.MonkeyPatch) -> None:
    served: list[object] = []

    class Server:
        def __init__(self, config: uvicorn.Config) -> None:
            served.append(config)

        def run(self) -> None:
            served.append("ran")

    environment.setattr(uvicorn, "Server", Server)
    environment.setattr(server, "make_app", lambda loaded: FastAPI())
    assert server.main(["--port", "7999"]) == 0
    config, ran = served
    assert isinstance(config, uvicorn.Config) and ran == "ran"
    assert (config.host, config.port, config.proxy_headers) == ("127.0.0.1", 7999, False)


def test_the_command_refuses_settings_it_cannot_run_with(
    environment: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment.setenv("OLE5_VOICE_ACCESS_CODE", "short-secret-1")
    assert server.main([]) == 2
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "OLE5_VOICE_ACCESS_CODE" in surfaces["stdout"]
    assert holding("short-secret-1", surfaces) == []


def test_the_module_runs_as_a_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["ole5_voice.server", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(Path(server.__file__)), run_name="__main__")
    assert exited.value.code == 0
    assert "--env-file" in capsys.readouterr().out


_TELEMETRY = """
import json, os
os.environ["FASTAPI_OTEL_AUTO_CONFIGURE"] = "true"
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

spans, logs, reader = InMemorySpanExporter(), InMemoryLogRecordExporter(), InMemoryMetricReader()
tracing = TracerProvider()
tracing.add_span_processor(SimpleSpanProcessor(spans))
trace.set_tracer_provider(tracing)
metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
logging = LoggerProvider()
logging.add_log_record_processor(SimpleLogRecordProcessor(logs))
set_logger_provider(logging)

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from ole5_voice.server import build_app
from ole5_voice.settings import AppSettings, Settings
from pydantic import SecretStr
from t2_agentic_voice import VoiceSettings

class Minter:
    def mint(self, caller, *, consent):
        return "made-up-token"

def fail():
    raise RuntimeError("a made-up failure")

def counts(app):
    router = APIRouter()
    router.add_api_route("/fail", fail)
    app.include_router(router, prefix="/voice")
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        consent = {"version": None, "record_audio": False}
        client.post("/token", json={"code": "x", "consent": consent})
        client.get("/voice/fail")
    data = reader.get_metrics_data()
    points = sum(
        len(metric.data.data_points)
        for resource in (data.resource_metrics if data else ())
        for scope in resource.scope_metrics
        for metric in scope.metrics
    )
    found = {"spans": len(spans.get_finished_spans()), "points": points}
    found["logs"] = len(logs.get_finished_logs())
    spans.clear(); logs.clear()
    return found

app_settings = AppSettings(access_code=SecretStr("x" * 20))
settings = Settings(app=app_settings, voice=VoiceSettings(env="dev"))
ole5 = counts(build_app(settings, router=APIRouter(), minter=Minter()))
control = counts(FastAPI(telemetry={"auto_configure": False}))
print(json.dumps({"ole5": ole5, "control": control}))
"""


def test_fastapis_telemetry_reaches_no_global_provider() -> None:
    """In a child process with a global tracer, meter and logger provider and
    FASTAPI_OTEL_AUTO_CONFIGURE=true, the Ole5 app's requests (the page, the token route and a
    route that fails) give no span, metric or log record; a FastAPI app with its telemetry left
    on, as a control, gives them."""
    child = subprocess.run(
        [sys.executable, "-c", _TELEMETRY],
        env=child_shell(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    found = json.loads(child.stdout.strip().splitlines()[-1])
    assert found["ole5"] == {"spans": 0, "points": 0, "logs": 0}
    assert min(found["control"].values()) > 0, found  # the providers do catch FastAPI's
