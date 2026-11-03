"""voice's entry point (voice/calls.py): every call of a runtime over Small WebRTC, from its offer
to its end, with the fakes' detectors and providers and a scripted session (kit.py), and a
local aiortc peer as the browser, given no ICE server (tests/conftest.py makes aiortc's
default list raise)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import TransportFailed
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.voice import pipeline as pipeline_module
from t2_agentic_voice.voice.calls import Calls, CallsFactory, Candidate, VoiceCalls
from t2_agentic_voice.voice.protocol import MAX_CLIENT_MESSAGE_BYTES, Stop
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    Connected,
    Ending,
    FromClient,
    TransportFailure,
)

from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import (
    Built,
    client_answered,
    client_offer,
    until,
    voice_calls,
)

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
ENGLISH = AGENT.languages[0]
END = Candidate(candidate="", sdp_mid="0", sdp_mline_index=0)  # the end of candidates


def _run(built: Built, body: Callable[[VoiceCalls], Awaitable[None]]) -> None:
    async def run() -> None:
        await built.calls.start()
        try:
            await body(built.calls)
        finally:
            await built.calls.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=60))


def test_voices_entry_point_meets_the_protocols_api_builds_it_with(settings: VoiceSettings) -> None:
    built: CallsFactory = VoiceCalls  # mypy checks that the runtime can build it
    calls: Calls = voice_calls(settings).calls  # and that it is the protocol api uses
    assert built is VoiceCalls and calls.phase("call-1") is None


def test_a_call_connects_takes_its_clients_messages_and_ends(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """A local peer offers, voice answers, ICE connects over this machine's addresses, the
    session greets, a `stop` on the data channel reaches it as that message, one whose compact
    JSON passes the bound is dropped with a line naming no part of it, and `end` closes the peer
    and forgets the call."""
    built = voice_calls(settings)
    caplog.set_level(logging.INFO)

    async def body(calls: VoiceCalls) -> None:
        peer, channel, offer = await client_offer()
        try:
            answer = await calls.answer(
                "call-1", offer, caller=CALLER, consent=CONSENT, language=ENGLISH
            )
            assert calls.phase("call-1") == "connecting" and "a=fingerprint" in answer
            await calls.add_candidates("call-1", [END])
            await client_answered(peer, answer)
            await until(lambda: calls.phase("call-1") == "connected")
            await until(lambda: channel.readyState == "open")
            channel.send(json.dumps({"v": 1, "type": "stop"}))
            padded = {"v": 1, "type": "stop", "pad": "x" * MAX_CLIENT_MESSAGE_BYTES}
            channel.send(json.dumps(padded))
            (session,) = built.script.sessions
            await until(lambda: any(isinstance(e, ClausePlayed) for e in session.events))
            await until(lambda: any(isinstance(e, FromClient) for e in session.events))
            await asyncio.sleep(0.3)
            await calls.end("call-1")
            assert calls.phase("call-1") is None
        finally:
            await peer.close()
        heard = [e.message for e in session.events if isinstance(e, FromClient)]
        assert heard == [Stop(v=1, type="stop")]
        assert isinstance(session.events[0], Connected) and session.closed
        assert any(isinstance(e, Ending) and e.reason == "server" for e in session.events)

    _run(built, body)
    dropped = [r for r in caplog.records if r.getMessage() == "client_message_dropped"]
    assert [getattr(r, FIELDS) for r in dropped] == [{"problems": ["too_large"]}]
    assert "xxxx" not in caplog.text


def test_a_call_not_connected_by_the_deadline_fails_at_connect(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An offer answered whose peer never takes the answer ends as a `TransportFailure` at
    `connect` once voice's deadline passes, with its `TransportFailed`, and is forgotten."""
    monkeypatch.setattr(pipeline_module, "CONNECT_DEADLINE_S", 0.3)
    built = voice_calls(settings)

    async def body(calls: VoiceCalls) -> None:
        peer, _, offer = await client_offer()
        try:
            await calls.answer("call-1", offer, caller=CALLER, consent=CONSENT, language=ENGLISH)
            await until(lambda: calls.phase("call-1") is None)
        finally:
            await peer.close()
        (session,) = built.script.sessions
        (failure,) = [e for e in session.events if isinstance(e, TransportFailure)]
        assert failure.stage == "connect"

    _run(built, body)
    assert [e.stage for e in built.emitted if isinstance(e, TransportFailed)] == ["connect"]
