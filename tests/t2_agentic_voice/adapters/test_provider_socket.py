"""What the adapters heard over a provider's WebSocket share (adapters/provider_socket.py): the
connection's options (no proxy, a logger that logs nothing, so no handshake header or frame,
a key among them, reaches a log), the finals' join, the chunks, and the failures' mapping."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import pytest
from t2_agentic_voice.adapters import provider_socket
from t2_agentic_voice.adapters.provider_socket import Piece, chunks, finals, open_socket

from tests.t2_agentic_voice.adapters.provider_support import KEY


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
