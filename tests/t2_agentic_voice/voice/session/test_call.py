"""The voice session (voice/session/call.py). Plan 003's Track D builds it and replaces this file's
stub test with its own, driving it with the fake session I/O."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import Command
from t2_agentic_voice.voice.session.io import CallSetup, Session
from t2_agentic_voice.voice.session.session_events import Connected


class _NoPhrases:
    def audio(self, text: str, *, language: str) -> AudioChunk:
        raise LookupError("not declared")


class _NoSide:
    async def run(self, command: Command) -> None:
        """Takes every command and does nothing."""


def test_the_session_is_a_stub_until_track_d(settings: VoiceSettings) -> None:
    english = Language.english(greeting="Hello there.")
    setup = CallSetup(
        call_id="call-1",
        caller=Caller(subject="made-up"),
        consent=Consent(version=None, record_audio=False),
        agent=VoiceAgent(name="echo", languages=[english]),
        language=english,
        settings=settings,
        phrases=_NoPhrases(),
        max_chars=lambda language: 200,
        tracing=Tracing(),
        emit=lambda event: None,
    )
    with pytest.raises(NotImplementedError, match="Track D"):
        CallSession(setup, _NoSide())
    stub = CallSession.__new__(CallSession)  # the methods' stubs, past the constructor's
    session: Session = stub  # mypy checks the protocol's shape
    with pytest.raises(NotImplementedError, match="Track D"):
        asyncio.run(session.handle(Connected(at=0.0)))
    with pytest.raises(NotImplementedError, match="Track D"):
        asyncio.run(session.aclose())
