"""What the chat adapter's tests share (test_groq_chat.py, test_groq_chat_errors.py,
test_groq_chat_checks.py): Groq's streamed chat answers built by hand as server-sent events
(made-up chunks in the shape Groq streams them, its `x_groq.usage` on the last), a request with
every kind of message, one request through `GroqChat` on a fake transport, and a server on
127.0.0.1 for the checks that need a real connection. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import socket
import threading
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatMessage,
    ChatRequest,
    ToolCallRequest,
    ToolSchema,
)

from tests.t2_agentic_voice.adapters.groq_support import KEY

SEARCH = ToolSchema(
    name="search_help",
    description="Search the help articles.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
)
EARLIER = ToolCallRequest(id="call_0", name="search_help", arguments='{"query":"made up"}')
MESSAGES = (
    ChatMessage.system("Answer in one short sentence."),
    ChatMessage.user("How do I reset my password?"),
    ChatMessage.assistant(tool_calls=(EARLIER,)),
    ChatMessage.tool_result("call_0", "Open Settings, then Security."),
    ChatMessage.assistant("Open Settings."),
    ChatMessage.user("And then?"),
)
REQUEST = ChatRequest(messages=MESSAGES, tools=(SEARCH,), model="openai/gpt-oss-120b")
USAGE = {"prompt_tokens": 822, "completion_tokens": 68, "total_tokens": 890, "queue_time": 0.01}
CACHED = USAGE | {"prompt_tokens_details": {"cached_tokens": 768}}


def chunk(
    delta: Mapping[str, Any] | None = None, finish: str | None = None, **extra: Any
) -> dict[str, Any]:
    """One chunk of a streamed chat answer: a delta of its one choice, and its finish reason."""
    choice = {"index": 0, "delta": dict(delta or {}), "logprobs": None, "finish_reason": finish}
    return {
        "id": "chatcmpl-made-up",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [choice],
    } | extra


def text(*pieces: str, finish: str = "stop", usage: Mapping[str, Any] | None = None) -> list[Any]:
    """The chunks of an answer in words: its role, the model's reasoning (which gpt-oss streams
    beside its text), each piece of text, then the end with Groq's usage."""
    end = chunk(finish=finish, x_groq={"id": "req_made_up", "usage": dict(usage or USAGE)})
    return [
        chunk({"role": "assistant", "content": ""}),
        chunk({"reasoning": "The made-up caller wants the steps."}),
        *(chunk({"content": piece}) for piece in pieces),
        end,
    ]


def call_piece(index: int, **piece: Any) -> dict[str, Any]:
    """A chunk with one piece of the tool call at `index`: its id, name or arguments' text."""
    function = {key: piece.pop(key) for key in ("name", "arguments") if key in piece}
    return chunk({"tool_calls": [{"index": index, **piece, "function": function}]})


def sse(*events: Any, done: bool = True) -> bytes:
    """`events` as a server-sent stream: a chunk as its data, a `(name, data)` pair as a named
    event, bytes as they are; then `[DONE]`, unless not `done`."""
    out = b""
    for event in events:
        if isinstance(event, bytes):
            out += event
        elif isinstance(event, tuple):
            name, data = event
            out += f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
        else:
            out += f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
    return out + (b"data: [DONE]\n\n" if done else b"")


def streamed(
    body: bytes, *, size: int = 64, fail: Exception | None = None, status: int = 200
) -> httpx.Response:
    """An answer whose body streams `body` in pieces of `size` bytes, then raises `fail` if
    given, as a network cuts it."""

    async def pieces() -> AsyncIterator[bytes]:
        for start in range(0, len(body), size):
            yield body[start : start + size]
        if fail is not None:
            raise fail

    headers = {"content-type": "text/event-stream"}
    return httpx.Response(status, headers=headers, content=pieces())


def chat_settings(timeout_s: float = 8.0, **groq: Any) -> VoiceSettings:
    """Settings holding the made-up `KEY`, unless `groq` gives the group's values."""
    given = GroqSettings(**({"api_key": SecretStr(KEY)} | groq))
    return VoiceSettings(env="test", groq=given, llm=LlmSettings(timeout_s=timeout_s))


async def ask(
    fake: httpx.AsyncBaseTransport, request: ChatRequest = REQUEST, **given: Any
) -> list[ChatEvent]:
    """Every event of one request through an adapter built from `chat_settings(**given)` on the
    `fake` transport, closed after it."""
    adapter = GroqChat.from_settings(chat_settings(**given), transport=fake)
    try:
        return [event async for event in adapter.stream(request)]
    finally:
        await adapter.aclose()


async def ask_partly(
    fake: httpx.AsyncBaseTransport, request: ChatRequest = REQUEST
) -> tuple[list[ChatEvent], ProviderError | None]:
    """The events of one request (as `ask`) up to its failure, and the failure: None when the
    stream ended."""
    adapter = GroqChat.from_settings(chat_settings(), transport=fake)
    seen: list[ChatEvent] = []
    try:
        async for event in adapter.stream(request):
            seen.append(event)
    except ProviderError as error:
        return seen, error
    finally:
        await adapter.aclose()
    return seen, None


def body_of(request: httpx.Request) -> dict[str, Any]:
    """The JSON body a request sent."""
    sent: dict[str, Any] = json.loads(request.content)
    return sent


class Local(httpx.AsyncHTTPTransport):
    """Sends every request over a real connection to a server on 127.0.0.1, at `port`."""

    port, closed = 0, False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        return await super().handle_async_request(request)

    async def aclose(self) -> None:
        await super().aclose()
        self.closed = True


class Server:
    """A server on 127.0.0.1 that answers every request on each connection with `answer` (an
    SSE body, sent whole), or, `stalling`, sends `answer` as the start of a chunked one and then
    nothing (with `answer` None, not even the answer's head), until the client hangs up; it
    counts the connections and requests it took."""

    def __init__(self, answer: bytes | None, *, stalling: bool = False) -> None:
        self.answer, self.stalling = answer, stalling
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(5)
        self.connections = self.requests = 0
        self.answered, self.hung_up = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self._accept, daemon=True)

    def _accept(self) -> None:
        with contextlib.suppress(OSError):
            while True:
                connection = self.listener.accept()[0]
                self.connections += 1
                threading.Thread(target=self._serve, args=(connection,), daemon=True).start()

    def _serve(self, connection: socket.socket) -> None:
        with contextlib.suppress(OSError), connection:
            buffer = b""
            while (request := self._request(connection, buffer)) is not None:
                buffer = request
                self.requests += 1
                head = "HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n"
                if self.answer is None:
                    pass  # the answer never comes
                elif self.stalling:
                    size = f"{len(self.answer):x}\r\n".encode()
                    connection.sendall(f"{head}transfer-encoding: chunked\r\n\r\n".encode())
                    connection.sendall(size + self.answer + b"\r\n")
                else:
                    length = f"content-length: {len(self.answer)}\r\n\r\n"
                    connection.sendall((head + length).encode() + self.answer)
                self.answered.set()
            self.hung_up.set()

    @staticmethod
    def _request(connection: socket.socket, buffer: bytes) -> bytes | None:
        """Reads one request (its head and its body); returns what came after it, None once the
        client has hung up."""
        while b"\r\n\r\n" not in buffer:
            if not (data := connection.recv(65536)):
                return None
            buffer += data
        head, _, rest = buffer.partition(b"\r\n\r\n")
        found = re.search(rb"content-length: *(\d+)", head, re.IGNORECASE)
        length = int(found.group(1)) if found else 0
        while len(rest) < length:
            if not (data := connection.recv(65536)):
                return None
            rest += data
        return rest[length:]

    def __enter__(self) -> Local:
        self.thread.start()
        transport = Local()
        transport.port = self.listener.getsockname()[1]
        return transport

    def __exit__(self, *_: object) -> None:
        self.listener.close()
        self.thread.join(5)


async def settle() -> set[asyncio.Task[Any]]:
    """The tasks still pending once the loop has settled, this one's aside: a stream closed
    between events leaves the SDK's and httpx's own async generators suspended, and each one's
    finalizer, a task, closes the next on a later turn of the loop."""
    for _ in range(100):
        left = asyncio.all_tasks() - {asyncio.current_task()}
        if not left:
            break
        await asyncio.sleep(0)
    return left
