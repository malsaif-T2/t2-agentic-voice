"""One turn over a provider's streaming WebSocket (D-100): for a provider whose speech-to-text
is a stream, one finished turn's audio is one connection, so the port's rule holds (one turn,
one request).

- `open_socket`: the connection, by the websockets package with no proxy (its default reads the
  proxy variables, which would send the key, the audio and the transcript elsewhere), no
  compression, no keepalive pings (a turn is short), and a logger that logs nothing: websockets'
  debug log writes the handshake's headers and every frame, a key among them.
- `hear_turn`: sends the opening messages, waits for the provider's ready message when it sends
  one, sends the audio in chunks (as fast as the socket takes them, or `gap_s` apart for an
  engine that must hear it near real time), then the closing messages, and reads what the
  provider heard: each message the vendor's `read` turns into a `Piece` (an error frame
  raises), as it comes, while the audio is still being sent. Once everything is sent, the turn
  ends when the provider closes the socket, or when `final_wait_s` passes with no final yet,
  or `quiet_s` with no message after one; the caller bounds the whole turn.
- `socket_failure`: every failure a ProviderError as `http_failure` makes one (the provider,
  the failure's class, a handshake's HTTP status or a close code), never a frame's text.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol, cast

from pydantic import JsonValue
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, InvalidStatus
from websockets.typing import LoggerLike

from t2_agentic_voice.adapters.provider_http import AnswerError, status_failure
from t2_agentic_voice.core.errors import ProviderError

Message = str | bytes
# The close codes that mean the provider refused the session (a bad key, a policy): not worth
# asking again; any other close is a lost connection.
_REFUSED_CODES: Final = frozenset({1008, 4001, 4003})
# The largest message the adapter reads, in bytes: a turn's transcript is far smaller.
MAX_MESSAGE: Final = 1 << 20
CLOSE_S: Final = 1.0  # the longest a turn's socket takes to close, in seconds
OPEN_S: Final = 10.0  # the longest its handshake takes, inside the turn's own bound


class Socket(Protocol):
    """What a turn needs of a WebSocket connection (websockets' `ClientConnection`, or a
    test's fake)."""

    async def send(self, message: Message) -> None: ...

    async def recv(self) -> Message: ...

    async def close(self) -> None: ...


# What opens a turn's socket: the URL, the handshake's headers and the open timeout in seconds
# (`open_socket`, or a test's fake).
Opener = Callable[[str, Mapping[str, str], float], Awaitable[Socket]]


@dataclass(frozen=True)
class Piece:
    """What one provider message says: its text, whether it is final, and its confidence."""

    text: str
    final: bool
    confidence: float | None = None


class _Silent:
    """A logger that logs nothing, for websockets (the module's docstring)."""

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 - the logging API's name
        return False

    def debug(self, *args: object, **kwargs: object) -> None:
        return None

    info = warning = error = exception = debug

    def log(self, level: int, *args: object, **kwargs: object) -> None:
        return None


async def open_socket(
    url: str, headers: Mapping[str, str], open_timeout_s: float, *, max_size: int = MAX_MESSAGE
) -> Socket:
    """The connection to `url` with `headers` sent on its handshake (the module's docstring),
    reading messages of up to `max_size` bytes (a streamed take's audio is larger than a
    turn's transcript)."""
    connection = await connect(
        url,
        additional_headers=dict(headers),
        proxy=None,
        compression=None,
        ping_interval=None,
        open_timeout=open_timeout_s,
        max_size=max_size,
        logger=cast(LoggerLike, _Silent()),
    )
    return cast(Socket, connection)


@dataclass(frozen=True)
class Turn:
    """What a turn sends: its opening messages, its audio chunks (`gap_s` apart) and its closing
    messages, and the ready message the provider sends before it takes audio, if it sends one."""

    opening: Sequence[Message]
    audio: Iterable[bytes]
    closing: Sequence[Message] = ()
    ready: Callable[[Message], bool] | None = None
    gap_s: float = 0.0


async def hear_turn(
    socket: Socket,
    turn: Turn,
    read: Callable[[Message], Piece | None],
    *,
    final_wait_s: float,
    quiet_s: float,
) -> list[Piece]:
    """Every piece the provider sent for `turn` on `socket`, in order (the module's docstring);
    the caller bounds the whole turn and closes the socket."""
    pieces: list[Piece] = []
    for message in turn.opening:
        await socket.send(message)
    while turn.ready is not None:
        message = await socket.recv()
        if turn.ready(message):
            break
        _keep(read(message), pieces)
    arrived = asyncio.Event()
    reading = asyncio.create_task(_read_all(socket, read, pieces, arrived))
    try:
        await _send_audio(socket, turn)
        while not reading.done():
            arrived.clear()
            wait_s = quiet_s if any(piece.final for piece in pieces) else final_wait_s
            came = asyncio.ensure_future(arrived.wait())
            done, _ = await asyncio.wait(
                {reading, came}, timeout=wait_s, return_when="FIRST_COMPLETED"
            )
            came.cancel()
            if not done:
                break  # quiet: nothing came in the wait
    finally:
        reading.cancel()
    failed = reading.exception() if reading.done() and not reading.cancelled() else None
    if failed is not None:
        raise failed
    return pieces


async def _send_audio(socket: Socket, turn: Turn) -> None:
    for chunk in turn.audio:
        await socket.send(chunk)
        if turn.gap_s:
            await asyncio.sleep(turn.gap_s)
    for message in turn.closing:
        await socket.send(message)


async def _read_all(
    socket: Socket,
    read: Callable[[Message], Piece | None],
    pieces: list[Piece],
    arrived: asyncio.Event,
) -> None:
    """Read the provider's messages into `pieces`, `arrived` set at each, until it closes the
    socket in order."""
    while True:
        try:
            message = await socket.recv()
        except ConnectionClosedOK:
            return
        _keep(read(message), pieces)
        arrived.set()


async def close_quietly(socket: Socket | None) -> None:
    """Close `socket`, best effort and within `CLOSE_S`: a failed close fails nothing."""
    if socket is None:
        return
    try:
        async with asyncio.timeout(CLOSE_S):
            await socket.close()
    except Exception:  # noqa: S110 - the turn's answer, or its failure, is already decided
        pass


def _keep(piece: Piece | None, pieces: list[Piece]) -> None:
    if piece is not None:
        pieces.append(piece)


def finals(pieces: Sequence[Piece]) -> tuple[str, float | None]:
    """The turn's final text, its final pieces joined with a space, and their mean confidence
    when each gives one."""
    kept = [piece for piece in pieces if piece.final and piece.text.strip()]
    text = " ".join(piece.text.strip() for piece in kept)
    scores = [piece.confidence for piece in kept if piece.confidence is not None]
    confidence = sum(scores) / len(scores) if kept and len(scores) == len(kept) else None
    return text, confidence


def chunks(pcm16: bytes, size: int) -> list[bytes]:
    """`pcm16` cut into chunks of `size` bytes, the last one shorter."""
    return [pcm16[start : start + size] for start in range(0, len(pcm16), size)]


def socket_failure(provider: str, error: Exception) -> ProviderError:
    """The ProviderError for one failure of a turn (the module's docstring): a refused
    handshake maps its status as `http_failure` does; a close the provider refused with is
    rejected, any other close a lost connection; a frame the vendor could not read, or an
    error frame, a server error not worth asking again for."""
    details: dict[str, JsonValue] = {"provider": provider, "error": type(error).__name__}
    if isinstance(error, AnswerError):
        details["error"] = error.reason
        return ProviderError("server_error", False, details=details)
    if isinstance(error, InvalidStatus):
        response = error.response
        return status_failure(details, response.status_code, response.headers.get("retry-after"))
    if isinstance(error, TimeoutError):
        return ProviderError("timeout", True, details=details)
    if isinstance(error, ConnectionClosed):
        code = error.rcvd.code if error.rcvd is not None else None
        details["close_code"] = code
        if code in _REFUSED_CODES:
            return ProviderError("rejected", False, details=details)
        return ProviderError("connection_lost", True, details=details)
    if isinstance(error, OSError):
        return ProviderError("connection_lost", True, details=details)
    return ProviderError("server_error", False, details=details)
