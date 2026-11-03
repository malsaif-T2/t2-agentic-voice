"""One call's transport (voice/transport.py): the offer and candidate checks before Pipecat sees
them, the peer's ICE servers, its bounded close, and the transport's parameters."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.voice import transport as transport_module
from t2_agentic_voice.voice.transport import (
    IN_RATE,
    OUT_RATE,
    WebRTCPeer,
    check_candidate,
    check_offer,
    transport_params,
)

from tests.t2_agentic_voice.voice.kit import client_offer

HOST = "candidate:842163049 1 udp 1677729535 192.0.2.10 54400 typ host generation 0"
RELAY = "candidate:3 1 udp 41885439 192.0.2.20 3478 typ relay raddr 192.0.2.30 rport 61000"
TCP = "candidate:4 1 tcp 1518280447 192.0.2.10 9 typ host tcptype active"


def test_an_offer_ending_its_candidates_with_none_usable_is_refused() -> None:
    """aioice 0.11.0 leaves such a peer `new` with no event (F7): refused, the offer named in
    no part; with a UDP candidate, or with no end of candidates, it passes."""
    head = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    with pytest.raises(InvalidRequestError) as refused:
        check_offer(head + "a=end-of-candidates\r\n")
    with pytest.raises(InvalidRequestError):
        check_offer(head + f"a={TCP}\r\na=end-of-candidates\r\n")
    assert "a=" not in str(refused.value)
    check_offer(head + f"a={HOST}\r\na=end-of-candidates\r\n")
    check_offer(head)


@pytest.mark.parametrize(
    "line",
    [
        "candidate:1 1 udp 1",  # too short
        "candidate:1 x udp 1677729535 192.0.2.10 54400 typ host",  # component not a number
        "candidate:1 0 udp 1677729535 192.0.2.10 54400 typ host",  # no such component
        "candidate:1 1 sctp 1677729535 192.0.2.10 54400 typ host",  # no such protocol
        "candidate:1 1 udp -5 192.0.2.10 54400 typ host",  # a negative priority
        "candidate:1 1 udp 1677729535 192.0.2.10 70000 typ host",  # a port past 65535
        "candidate:1 1 udp 1677729535 192.0.2.10 54400 type host",  # not `typ`
        "candidate:1 1 udp 1677729535 192.0.2.10 54400 typ local",  # no such type
        "candidate:1 1 udp 1677729535 192.0.2.10 54400 typ host generation",  # a name alone
        "candidate:1 1 udp 1677729535 192.0.2.10 54400 typ relay rport many",  # not a port
    ],
)
def test_a_candidate_aiortc_cannot_read_is_refused_naming_none_of_it(line: str) -> None:
    with pytest.raises(InvalidRequestError) as refused:
        check_candidate(line)
    assert "192.0.2" not in str(refused.value) and refused.value.details == {}


def test_a_candidate_a_browser_sends_is_read() -> None:
    for line in (HOST, RELAY, TCP, HOST.removeprefix("candidate:")):
        check_candidate(line)


def test_a_calls_transport_hears_mono_at_the_detectors_rate_and_speaks_at_the_pipelines() -> None:
    params = transport_params()
    assert (params.audio_in_enabled, params.audio_out_enabled) == (True, True)
    assert (params.audio_in_sample_rate, params.audio_in_channels) == (IN_RATE, 1) == (16_000, 1)
    assert (params.audio_out_sample_rate, OUT_RATE, params.audio_out_end_silence_secs) == (
        24_000,
        24_000,
        0,
    )


def test_a_peer_gets_exactly_the_ice_servers_it_is_given() -> None:
    """None for an empty list, never aiortc's default (which tests/conftest.py makes raise), and
    the settings' servers as given otherwise; its candidates are read before Pipecat sees
    them, and its close is bounded."""

    async def run() -> tuple[list[object], list[object]]:
        servers: list[list[object]] = []
        for given in ([], ["stun:stun.example.test:3478"]):
            client, _, offer = await client_offer()
            peer = await WebRTCPeer.answer(offer, given)
            servers.append([s.urls for s in peer.connection.ice_servers])
            with pytest.raises(InvalidRequestError):
                await peer.add_candidates([("candidate:1 1 udp 1", "0", 0)])
            await peer.add_candidates([(HOST, "0", 0), ("", "0", 0)])
            await peer.close()
            await client.close()
        return servers[0], servers[1]

    assert asyncio.run(run()) == ([], ["stun:stun.example.test:3478"])


def test_an_offer_aiortc_cannot_read_is_refused_naming_none_of_it() -> None:
    async def run() -> None:
        await WebRTCPeer.answer("v=0\r\nm=audio x secret\r\n", [])

    with pytest.raises(InvalidRequestError) as refused:
        asyncio.run(run())
    assert "secret" not in str(refused.value) and refused.value.__cause__ is None


def test_a_close_that_hangs_or_fails_is_bounded_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Windows' proactor loop can hang a peer's close (plan 003's appendix, item 20): the close
    gives up after `CLOSE_TIMEOUT_S`, and one that raises is logged by its type, so the call is
    forgotten either way."""
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(transport_module, "CLOSE_TIMEOUT_S", 0.05)

    async def run() -> None:
        client, _, offer = await client_offer()
        peer = await WebRTCPeer.answer(offer, [])

        async def hang() -> None:
            await asyncio.sleep(10)

        async def fail() -> None:
            raise OSError("the socket's own text")

        real = peer.connection.disconnect
        for odd in (hang, fail):
            monkeypatch.setattr(peer.connection, "disconnect", odd)
            await peer.close()
        monkeypatch.setattr(peer.connection, "disconnect", real)
        await peer.close()
        await client.close()

    asyncio.run(run())
    lines = [r.getMessage() for r in caplog.records]
    assert "peer_close_timeout" in lines and "peer_close_failed" in lines
    assert "own text" not in caplog.text
