"""What the adapters heard over a provider's WebSocket share (adapters/provider_socket.py): the
connection's options (no proxy, a logger that logs nothing, so no handshake header or frame,
a key among them, reaches a log), a turn's reading and its end, the finals' join and the
chunks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

import pytest
from t2_agentic_voice.adapters import provider_socket
from t2_agentic_voice.adapters.provider_socket import (
    Piece,
    Turn,
    chunks,
    finals,
    hear_turn,
    open_socket,
)
from websockets.exceptions import ConnectionClosed

from tests.t2_agentic_voice.adapters.provider_support import KEY, FakeSocket, Message, closed


def test_the_connection_takes_no_proxy_no_compression_and_logs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 5: websockets' default reads the proxy variables, and its debug log writes the
    handshake's headers, the bearer key among them."""
    given: dict[str, object] = {}

    async def connect(url: str, **options: object) -> str:
        given.update(options, url=url)
        return "connection"

    monkeypatch.setattr(provider_socket, "connect", connect)
    headers: Mapping[str, str] = {"authorization": f"Bearer {KEY}"}
    connection: object = asyncio.run(open_socket("wss://provider.example/stt", headers, 3.0))
    assert connection == "connection"
    logger: Any = given.pop("logger")
    assert given == {
        "url": "wss://provider.example/stt",
        "additional_headers": {"authorization": f"Bearer {KEY}"},
        "proxy": None,
        "compression": None,
        "ping_interval": None,
        "open_timeout": 3.0,
        "max_size": 1 << 20,
    }
    levels = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
    assert not any(logger.isEnabledFor(level) for level in levels)
    for method in ("debug", "info", "warning", "error", "exception"):
        assert getattr(logger, method)("> %s", KEY) is None
    assert logger.log(logging.ERROR, KEY) is None


def test_the_finals_are_joined_and_their_confidence_kept_only_when_each_gives_one() -> None:
    pieces = [
        Piece("a ", True, 0.5),
        Piece("partial", False, 0.1),
        Piece(" ", True),
        Piece("b", True, 1.0),
    ]
    assert finals(pieces) == ("a b", 0.75)
    assert finals([Piece("a", True, 0.5), Piece("b", True)]) == ("a b", None)
    assert finals([Piece("only partial", False)]) == ("", None)


def test_the_audio_is_cut_into_whole_chunks_and_a_shorter_last_one() -> None:
    assert chunks(bytes(10), 4) == [bytes(4), bytes(4), bytes(2)]
    assert chunks(b"", 4) == []


def _piece(message: Message) -> Piece | None:
    text = message if isinstance(message, str) else message.decode()
    return Piece(text.removeprefix("final:"), text.startswith("final:"))


def _hear(socket: FakeSocket, *, final_wait_s: float, quiet_s: float) -> tuple[list[Piece], float]:
    turn = Turn(opening=("hello",), audio=[b"a", b"b"], closing=("bye",))
    started = time.monotonic()
    pieces = asyncio.run(
        hear_turn(socket, turn, _piece, final_wait_s=final_wait_s, quiet_s=quiet_s)
    )
    return pieces, time.monotonic() - started


def test_what_comes_while_the_audio_is_sent_is_read_and_a_close_ends_the_turn() -> None:
    socket = FakeSocket(lambda m: ["final:one"] if m == b"a" else [closed()] if m == "bye" else [])
    pieces, took = _hear(socket, final_wait_s=5, quiet_s=5)
    assert pieces == [Piece("one", True)] and took < 2
    assert socket.sent == ["hello", b"a", b"b", "bye"]


def test_a_turn_waits_longer_for_its_first_final_than_for_the_quiet_after_one() -> None:
    partial = FakeSocket(lambda m: ["partial"] if m == "bye" else [])
    pieces, took = _hear(partial, final_wait_s=0.3, quiet_s=0.01)
    assert pieces == [Piece("partial", False)] and took >= 0.25
    final = FakeSocket(lambda m: ["final:done"] if m == "bye" else [])
    pieces, took = _hear(final, final_wait_s=0.01, quiet_s=0.3)
    assert pieces == [Piece("done", True)] and took >= 0.25


def test_a_failed_read_fails_the_turn() -> None:
    socket = FakeSocket(lambda m: [closed(1011)] if m == "bye" else [])
    with pytest.raises(ConnectionClosed):
        _hear(socket, final_wait_s=5, quiet_s=5)
