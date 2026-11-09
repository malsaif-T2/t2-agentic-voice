"""Which agent the Ole5 app's server runs (ole5_voice/server.py): the talker, searching the
knowledge base, when all three of `QDRANT_URL`, `QDRANT_LOGIN_EMAIL` and
`QDRANT_LOGIN_PASSWORD` are set; the echo, said once in a log line, when none is; a refusal to
start, naming the ones missing, when only some are. The knowledge base's client is closed as
the app's lifespan ends, after the runtime's. The runtime and the tokens are fakes, as in
test_server.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, ClassVar

import pytest
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from ole5_voice import agent, server
from ole5_voice.agent import ECHO_AGENT, PROGRESS_KEY, SEARCH_LIMIT
from ole5_voice.settings import AppSettings, KnowledgeAccess, Settings, knowledge_access
from pydantic import SecretStr
from t2_agentic_voice import ConfigurationError, VoiceSettings

from tests.leaks import holding, shown

CODE = "made-up-access-code-0123"
PASSWORD = "made-up-kb-password-0123"
ACCESS = {
    "qdrant_url": "https://made-up.example/team/qdrant",
    "qdrant_login_email": "someone@example.com",
    "qdrant_login_password": SecretStr(PASSWORD),
}


def _settings(**access: Any) -> Settings:
    app = AppSettings(access_code=SecretStr(CODE)).model_copy(update=access)
    return Settings(app=app, voice=VoiceSettings(env="dev"))


class _Tokens:
    @classmethod
    def from_settings(cls, join: object, *, prefix: str) -> _Tokens:
        return cls()

    def mint(self, caller: object, *, consent: object) -> str:
        return "made-up-token"


class _Runtime:
    """Stands in for `VoiceRuntime`: keeps the agent it was given, and its router's lifespan
    writes to `happened`."""

    made: ClassVar[list[_Runtime]] = []
    happened: ClassVar[list[str]] = []

    def __init__(self, agent: object, *, settings: VoiceSettings, identity: object) -> None:
        self.agent = agent
        _Runtime.made.append(self)

    def router(self) -> APIRouter:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            _Runtime.happened.append("runtime started")
            yield
            _Runtime.happened.append("runtime stopped")

        return APIRouter(lifespan=lifespan)


class _KnowledgeBase:
    """Stands in for `QdrantKnowledgeBase`: keeps its access, and writes its close."""

    made: ClassVar[list[_KnowledgeBase]] = []

    def __init__(self, access: KnowledgeAccess) -> None:
        self.access = access
        _KnowledgeBase.made.append(self)

    async def warm_up(self) -> None:
        _Runtime.happened.append("knowledge base warmed up")

    async def aclose(self) -> None:
        _Runtime.happened.append("knowledge base closed")


class _Tool:
    name = "search_knowledge"
    description = "Search the made-up base."
    progress = PROGRESS_KEY


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """The runtime, the tokens, the knowledge base and the library's knowledge tool, faked; the
    list of the bases each search tool was made of, each checked to read Ole5's one k."""
    searched: list[object] = []

    def knowledge_tool(kb: object, **given: object) -> _Tool:
        assert given["limit"] == SEARCH_LIMIT  # the k every run's agent reads too
        searched.append(kb)
        return _Tool()

    monkeypatch.setattr(server, "VoiceRuntime", _Runtime)
    monkeypatch.setattr(server, "SignedJoinTokens", _Tokens)
    monkeypatch.setattr(server, "QdrantKnowledgeBase", _KnowledgeBase)
    monkeypatch.setattr(agent, "knowledge_tool", knowledge_tool)
    for made in (_Runtime.made, _Runtime.happened, _KnowledgeBase.made):
        made.clear()
    return searched


def _lines(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, object]]:
    return [vars(r)["fields"] for r in caplog.records if r.getMessage() == event]


def test_with_no_knowledge_base_the_app_runs_the_echo_and_says_so_once(
    fakes: list[object], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    app = server.make_app(_settings())
    [runtime] = _Runtime.made
    assert runtime.agent is ECHO_AGENT
    assert _KnowledgeBase.made == [] and fakes == []
    assert _lines(caplog, "knowledge_base_not_set") == [
        {"agent": "echo", "fix": "set QDRANT_URL, QDRANT_LOGIN_EMAIL, QDRANT_LOGIN_PASSWORD"}
    ]
    assert _lines(caplog, "knowledge_base_set") == []
    with TestClient(app):
        pass
    assert _Runtime.happened == ["runtime started", "runtime stopped"]  # nothing else to close


def test_with_the_knowledge_base_set_the_app_runs_the_talker_with_its_search(
    fakes: list[object], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    loaded = _settings(**ACCESS)
    app = server.make_app(loaded)
    [runtime] = _Runtime.made
    [kb] = _KnowledgeBase.made
    assert kb.access == knowledge_access(loaded.app)
    assert fakes == [kb]  # the search is made of that knowledge base
    talker = runtime.agent
    assert isinstance(talker, type(ECHO_AGENT)) and talker.instructed
    assert [tool.name for tool in talker.tools] == ["search_knowledge"]
    assert _lines(caplog, "knowledge_base_set") == [{"agent": "talker"}]
    assert _lines(caplog, "knowledge_base_not_set") == []
    assert _Runtime.happened == []
    with TestClient(app):
        assert _Runtime.happened == ["runtime started", "knowledge base warmed up"]
    assert _Runtime.happened == [
        "runtime started",
        "knowledge base warmed up",
        "runtime stopped",
        "knowledge base closed",
    ]
    assert holding(PASSWORD, shown(caplog=caplog)) == []


def test_the_app_refuses_a_knowledge_base_set_only_in_part(fakes: list[object]) -> None:
    partial = {"qdrant_url": ACCESS["qdrant_url"]}
    with pytest.raises(ConfigurationError, match="QDRANT_LOGIN_EMAIL and QDRANT_LOGIN_PASSWORD"):
        server.make_app(_settings(**partial))
    assert _Runtime.made == [] and _KnowledgeBase.made == []


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_JOIN__KEYS", '{"k1": "a-made-up-join-key-of-forty-bytes-0123456"}')
    monkeypatch.setenv("T2V_JOIN__CURRENT_KID", "k1")
    monkeypatch.setenv("OLE5_VOICE_ACCESS_CODE", CODE)
    return monkeypatch


def test_the_command_refuses_to_start_with_the_access_set_in_part(
    environment: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment.setenv("QDRANT_LOGIN_EMAIL", "someone@example.com")
    environment.setenv("QDRANT_LOGIN_PASSWORD", PASSWORD)
    assert server.main([]) == 2
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "server_not_started" in surfaces["stdout"]
    assert "QDRANT_URL is not set" in surfaces["stdout"]
    assert holding(PASSWORD, surfaces) == []
    assert holding("someone@example.com", surfaces) == []


def test_the_command_writes_which_agent_runs_once_its_logs_are_set(
    environment: pytest.MonkeyPatch, fakes: list[object], capsys: pytest.CaptureFixture[str]
) -> None:
    """The line saying the app runs the echo reaches the command's output: the app is made
    after the logs are set. A refusal while the app is made is the command's refusal too."""
    served: list[object] = []

    class Server:
        def __init__(self, config: object) -> None:
            served.append(config)

        def run(self) -> None:
            served.append("ran")

    environment.setattr(uvicorn, "Server", Server)
    assert server.main([]) == 0
    assert "knowledge_base_not_set" in capsys.readouterr().out

    def refused(settings: Settings) -> FastAPI:
        raise ConfigurationError("made up: the app cannot be made. FIX: made up.")

    environment.setattr(server, "make_app", refused)
    assert server.main([]) == 2
    out = capsys.readouterr().out
    assert "server_not_started" in out and "the app cannot be made" in out
