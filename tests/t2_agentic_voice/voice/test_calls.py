"""voice's entry point (voice/calls.py): every call of a runtime over Small WebRTC, from its offer
to its end, with the fakes' detectors and providers and a scripted session (kit.py), and a
local aiortc peer as the browser, given no ICE server (tests/conftest.py makes aiortc's
default list raise)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from aiortc import RTCPeerConnection
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import (
    ConfigurationError,
    InvalidRequestError,
    NotFoundError,
    T2VoiceError,
)
from t2_agentic_voice.core.events import TransportFailed
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.voice import calls as calls_module
from t2_agentic_voice.voice import pipeline as pipeline_module
from t2_agentic_voice.voice import transport as transport_module
from t2_agentic_voice.voice.calls import (
    REFUSED_VARIABLES,
    TICKER_BOUND_S,
    Calls,
    CallsFactory,
    Candidate,
    VoiceCalls,
)
from t2_agentic_voice.voice.protocol import MAX_CLIENT_MESSAGE_BYTES, Stop
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    Connected,
    Ending,
    FromClient,
    TransportFailure,
)

from tests.t2_agentic_voice.fakes import (
    Captured,
    FakeSpeechToText,
    FakeTextToSpeech,
    capturing_output,
)
from tests.t2_agentic_voice.session_fakes import AGENT, FakePhrases
from tests.t2_agentic_voice.voice.kit import (
    Built,
    ToneVAD,
    client_answered,
    client_offer,
    until,
    voice_calls,
)

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
ENGLISH = AGENT.languages[0]
END = Candidate(candidate="", sdp_mid="0", sdp_mline_index=0)  # the end of candidates


async def _answer(calls: VoiceCalls, call_id: str, offer: str) -> str:
    return await calls.answer(call_id, offer, caller=CALLER, consent=CONSENT, language=ENGLISH)


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


@pytest.mark.parametrize("variable", REFUSED_VARIABLES)
def test_start_refuses_a_pipecat_variable_that_changes_every_call(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "made-up-value")
    with pytest.raises(ConfigurationError) as refused:
        asyncio.run(voice_calls(settings).calls.start())
    assert variable in str(refused.value) and "FIX:" in str(refused.value)
    assert "made-up-value" not in str(refused.value)
    assert refused.value.details == {"variables": [variable]}


def test_start_holds_the_transport_loggers_unless_a_call_may_log_its_content(
    tmp_path: Path,
) -> None:
    aioice = logging.getLogger("aioice")
    for content, level in ((True, logging.NOTSET), (False, logging.WARNING)):
        aioice.setLevel(logging.NOTSET)
        settings = VoiceSettings(
            env="dev",
            logging=LoggingSettings(content=content),
            storage=StorageSettings(var_dir=tmp_path / "var"),
        )
        asyncio.run(voice_calls(settings).calls.start())
        assert aioice.level == level


def test_start_warms_silero_and_smart_turn_when_given_no_detectors(
    settings: VoiceSettings, tmp_path: Path
) -> None:
    """With no factories voice builds Silero VAD and Smart Turn v3.2 from the settings, on the
    CPU, with no torch; with Smart Turn off, it builds no turn analyzer."""
    calls = VoiceCalls(
        agent=AGENT,
        settings=settings,
        stt=FakeSpeechToText(),
        tts=FakeTextToSpeech(),
        phrases=FakePhrases.of(AGENT),
        tracing=Tracing(),
        emit=lambda event: None,
    )
    asyncio.run(calls.start())
    detector, analyzer = calls._detectors()
    assert type(detector).__name__ == "SileroVADAnalyzer"
    assert type(analyzer).__name__ == "LocalSmartTurnAnalyzerV3"
    assert "torch" not in sys.modules
    off = VoiceSettings(
        env="test",
        turns=TurnSettings(smart_turn=False),
        storage=StorageSettings(var_dir=tmp_path / "var"),
    )
    built = voice_calls(off)
    assert built.calls._detectors()[1] is None and built.analyzers == []


def test_voice_builds_each_calls_session_as_the_session_module_gives_it(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[object] = []

    def session(setup: object, commands: object) -> object:
        made.append((setup, commands))
        return made

    monkeypatch.setattr(calls_module, "CallSession", session)
    calls = voice_calls(settings).calls
    pipeline = calls._pipeline(
        "call-1",
        (ToneVAD(), None),
        caller=CALLER,
        consent=CONSENT,
        language=ENGLISH,
        output=capturing_output(Captured()),
    )
    VoiceCalls._session(calls, pipeline)
    assert made == [(pipeline.setup, pipeline.commands)]


def test_an_offer_before_start_twice_or_that_aioice_hangs_on_is_refused(
    settings: VoiceSettings,
) -> None:
    built = voice_calls(settings)

    async def run() -> None:
        peer, _, offer = await client_offer()
        try:
            with pytest.raises(RuntimeError, match="FIX"):
                await _answer(built.calls, "call-1", offer)
            await built.calls.start()
            warmed = len(built.analyzers)
            hangs = "v=0\r\na=end-of-candidates\r\n"
            with pytest.raises(InvalidRequestError):  # F7: refused before any model is built
                await _answer(built.calls, "call-1", hangs)
            assert len(built.analyzers) == warmed
            await _answer(built.calls, "call-1", offer)
            with pytest.raises(InvalidRequestError):
                await _answer(built.calls, "call-1", offer)
        finally:
            await built.calls.aclose()
            await peer.close()

    asyncio.run(asyncio.wait_for(run(), timeout=60))


def test_a_call_whose_pipeline_does_not_start_is_refused_its_peer_closed(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline_module, "START_TIMEOUT_S", 0.0)
    monkeypatch.setattr(pipeline_module, "CLOSE_TIMEOUT_S", 0.5)
    closed: list[object] = []
    close = transport_module.WebRTCPeer.close

    async def closing(peer: transport_module.WebRTCPeer) -> None:
        closed.append(peer)
        await close(peer)

    monkeypatch.setattr(transport_module.WebRTCPeer, "close", closing)
    built = voice_calls(settings)

    async def body(calls: VoiceCalls) -> None:
        peer, _, offer = await client_offer()
        with pytest.raises(T2VoiceError, match="could not start"):
            await _answer(calls, "call-1", offer)
        await peer.close()
        assert calls.phase("call-1") is None and len(closed) == 1

    _run(built, body)


def test_building_a_calls_detectors_never_stalls_the_loop(settings: VoiceSettings) -> None:
    """Each call's detectors load their models off the event loop: while `answer` builds a call
    whose detector takes 0.2 s, a 20 ms ticker misses no deadline by `TICKER_BOUND_S`."""

    def slow() -> ToneVAD:
        time.sleep(0.2)
        return ToneVAD()

    built = voice_calls(settings, speech_detector=slow)
    late: list[float] = []

    async def ticker() -> None:
        start = time.perf_counter()
        for n in range(1, 40):
            due = start + n * 0.02
            await asyncio.sleep(max(0.0, due - time.perf_counter()))
            late.append(time.perf_counter() - due)

    async def body(calls: VoiceCalls) -> None:
        peer, _, offer = await client_offer()
        ticking = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        await _answer(calls, "call-1", offer)
        await ticking
        await peer.close()

    _run(built, body)
    assert len(late) == 39 and max(late) < TICKER_BOUND_S


def test_candidates_go_only_to_a_held_call_and_only_once_read(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    built = voice_calls(settings)
    bad = Candidate(candidate="candidate:1 1 udp 1", sdp_mid="0", sdp_mline_index=0)

    async def gone(peer: object, candidates: object) -> None:
        raise RuntimeError("Pipecat's own text")

    async def body(calls: VoiceCalls) -> None:
        peer, _, offer = await client_offer()
        with pytest.raises(NotFoundError):
            await calls.add_candidates("call-1", [END])
        await _answer(calls, "call-1", offer)
        with pytest.raises(InvalidRequestError):
            await calls.add_candidates("call-1", [bad])
        with monkeypatch.context() as patch:
            patch.setattr(transport_module.WebRTCPeer, "add_candidates", gone)
            with pytest.raises(NotFoundError):
                await calls.add_candidates("call-1", [END])
        await calls.end("call-1")
        with pytest.raises(NotFoundError):
            await calls.add_candidates("call-1", [END])
        await peer.close()

    _run(built, body)
    assert "candidates_not_taken" in caplog.text and "own text" not in caplog.text


def _ends(session: object) -> list[tuple[str, str]]:
    events = getattr(session, "events", [])
    found = [(type(e).__name__, e.stage) for e in events if isinstance(e, TransportFailure)]
    return found + [(type(e).__name__, e.reason) for e in events if isinstance(e, Ending)]


def test_a_peer_that_fails_or_closes_ends_its_call(settings: VoiceSettings) -> None:
    """ICE failing before the call connected is a `TransportFailure` at `connect`, after it at
    `media`; the caller's side closing a connected call is its `Ending`, `caller_left`."""
    built = voice_calls(settings)

    async def call(calls: VoiceCalls, call_id: str, *, connect: bool) -> RTCPeerConnection:
        peer, _, offer = await client_offer()
        answer = await _answer(calls, call_id, offer)
        if connect:
            await client_answered(peer, answer)
            await until(lambda: calls.phase(call_id) == "connected")
        return peer

    async def body(calls: VoiceCalls) -> None:
        peers = [await call(calls, "early", connect=False)]
        peers.append(await call(calls, "late", connect=True))
        for call_id in ("early", "late"):  # ICE failed: Pipecat's connection event
            connection = calls._calls[call_id].peer.connection
            await connection._call_event_handler("failed")
        peers.append(await call(calls, "left", connect=True))
        await peers[-1].close()
        await until(lambda: all(calls.phase(c) is None for c in ("early", "late", "left")))
        for peer in peers:
            await peer.close()

    _run(built, body)
    assert [_ends(s) for s in built.script.sessions] == [
        [("TransportFailure", "connect")],
        [("TransportFailure", "media")],
        [("Ending", "caller_left")],
    ]
    failed = [e.stage for e in built.emitted if isinstance(e, TransportFailed)]
    assert failed == ["connect", "media"]
