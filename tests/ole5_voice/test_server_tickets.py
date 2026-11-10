"""Ole5's talker with its tickets, served (ole5_voice/server.py; plan 007's integration): the
library's real `VoiceRuntime` of `talker_agent(kb, tickets=...)`, on a fake knowledge base and
fake providers, builds and runs its lifespan with `storage.var_dir` under the test's own folder,
opening the agent's outbox there and never under a `var/` of the repository's; and `build_app`
with the same mock serves `/tickets`, listing what the talker's own `create_ticket` made in it.
Nothing reaches a network: the speech providers and the chat model are fakes, the knowledge
base the library's `FakeKnowledgeBase`, and voice's detectors load their bundled models."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from ole5_voice.agent import talker_agent
from ole5_voice.server import build_app
from ole5_voice.settings import AppSettings, Settings
from ole5_voice.tickets.drafts import TicketMade
from ole5_voice.tickets.mock import MockTicketSystem
from pydantic import SecretStr
from t2_agentic_voice import (
    Action,
    Caller,
    Consent,
    Providers,
    StorageSettings,
    VoiceAgent,
    VoiceRuntime,
    VoiceSettings,
)
from t2_agentic_voice.evals import FakeKnowledgeBase, ScriptedLLM
from t2_agentic_voice.identity import DevIdentity
from t2_agentic_voice.ports import AudioChunk, AudioClip, DataFlow, Transcript

from tests.ole5_voice.tickets.action_support import action_context
from tests.ole5_voice.tickets.ticket_support import SUMMARY

CODE = "made-up-access-code-0123"
FLOW = DataFlow(provider="none", processed_in="the test", stored_in="nowhere", retention="none")
# The fake text-to-speech's rate, and how long each text it says lasts.
RATE, SAID_S = 24_000, 0.05


class _Silence:
    """A speech-to-text that hears nothing."""

    name = "fake"
    data_flow = FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        return Transcript(text="", language=language)

    async def aclose(self) -> None:
        """Nothing to close."""


class _Tone:
    """A text-to-speech that says every text as a short tone, and keeps each text it said."""

    name = "fake"
    data_flow = FLOW

    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def max_chars(self, language: str) -> int | None:
        return 200

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.said.append((text, language))
        samples = round(SAID_S * RATE)
        yield AudioChunk(pcm16=b"\x00\x04\x00\xfc" * (samples // 2), sample_rate=RATE)

    async def check_language(self, language: str) -> datetime | None:
        return None

    async def aclose(self) -> None:
        """Nothing to close."""


class _Minter:
    def mint(self, caller: Caller, *, consent: Consent) -> str:
        return "made-up-token"


def _create_ticket(agent: VoiceAgent) -> Action:
    (found,) = [t for t in agent.tools if isinstance(t, Action) and t.name == "create_ticket"]
    return found


def test_the_talker_with_tickets_serves_its_outbox_and_page_from_the_tests_folder(
    tmp_path: Path,
) -> None:
    voice = VoiceSettings(env="dev", storage=StorageSettings(var_dir=tmp_path / "var"))
    tickets = MockTicketSystem(tmp_path / "tickets")
    agent = talker_agent(FakeKnowledgeBase(), tickets=tickets)
    tts = _Tone()
    runtime = VoiceRuntime(
        agent,
        settings=voice,
        identity=DevIdentity(),
        providers=Providers(stt=_Silence(), tts=tts, chat=ScriptedLLM([])),
    )
    settings = Settings(app=AppSettings(access_code=SecretStr(CODE)), voice=voice)
    app = build_app(settings, router=runtime.router(), minter=_Minter(), tickets=tickets)
    outbox = voice.storage.var_dir / agent.name / "outbox.sqlite3"
    assert not outbox.exists()  # built with no IO
    create = _create_ticket(agent)
    draft = create.draft.model_validate({"summary": SUMMARY, "type": "Inquiry"})
    with TestClient(app, client=("127.0.0.1", 50000)) as test:
        assert outbox.is_file()  # opened as the lifespan started, under the test's folder
        assert test.get("/voice/health").status_code == 200
        assert SUMMARY not in test.get("/tickets").text  # no ticket yet
        made = asyncio.run(create.execute(ctx=action_context(), draft=draft))
        assert isinstance(made, TicketMade)
        page = test.get("/tickets")
        assert page.status_code == 200
        assert made.number in page.text and SUMMARY in page.text
    assert [ticket.number for ticket in tickets.listed()] == [made.number]
    written = sorted(p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file())
    assert set(written) == {"var", "tickets"}  # the runtime's files and the mock's, nowhere else
    assert tts.said  # the agent's fixed phrases, said once as the runtime started
