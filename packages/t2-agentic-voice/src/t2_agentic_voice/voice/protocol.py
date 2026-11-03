"""The `t2v/1` messages on a call's data channel (the design's 5.5): what the client sends the
session, and what the session sends the client. Each is a JSON object carrying `"v": 1` and a
`type` from a closed list; the HTTP bodies that set the call up are api/protocol.py's. Provisional,
but for the version check at join.

The browser is not trusted (docs/SECURITY.md's trust boundaries), so `parse_client_message`
parses a client's message strictly: one of the client's types, with exactly its fields, each of
its JSON type (no "1" or 1.0 for an integer, no 1 for a boolean), every size bounded, and the
message as the session gets it at most MAX_CLIENT_MESSAGE_BYTES of UTF-8; anything else is an
InvalidRequestError that holds none of it. No client message can set the caller's identity or
consent (the design's 5.5). The bound is on what the session gets: on a call's path, the object
Pipecat parsed, written back as compact UTF-8 JSON; on the text path, the text's own bytes.
Pipecat parses the data channel's text before that, with no bound of ours (up to the
transport's message size: aiortc advertises 64 KB), and holds the messages that come before the
call connects; so a message padded with whitespace past the bound reaches a call within it, and
a key the text held twice reaches a call with its last value.

The caller speaks in turns and the agent in replies, and neither shares the other's numbers: a
caller's turn is numbered by the speech-to-text bridge (`TurnId`), and each reply of the
agent's by the session, from 0, the greeting reply 0 and each echo and each spoken notice the
next (`ReplyId`), spoken clause by clause (`ClauseIndex`). An agent's caption and a client's
`playback` report name a clause by its reply and its index, so the greeting's first clause and
a turn's echo never share a key.

SmallWebRTC, which carries the messages, keeps two names for itself (Pipecat 1.15.0's
`transports/smallwebrtc/connection.py`, lines 82 and 376-380; plan 003's appendix, item 13): a
message typed `signalling` is its own, and raw text starting with `ping` its keep-alive. Every
`t2v/1` message is a JSON object with a `type`, and none has either name.

Plain pydantic with no Pipecat: the session (`voice/session/`, which imports no Pipecat) parses
and builds them, and Pipecat's transport only carries them, inbound through its `on_app_message`
event, outbound as urgent transport messages, so a stop never drops one (the appendix, item 8).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.core.events import MAX_INDEX, CallId, ClientConnection, EndReason, TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import NoticeKind

# The protocol's version: every message carries it as "v", and /join checks the client's.
PROTOCOL: Final = 1
# The most bytes of UTF-8 a client's message holds as the session gets it (the agent's bound):
# Pipecat's object written back as compact JSON on a call's path, the text itself on the text
# path, never the data channel's own text (above). The longest valid message, a `client_stats`
# with every field at its longest, fits in it several times over (a test).
MAX_CLIENT_MESSAGE_BYTES = 1024
# What SmallWebRTC keeps for itself on the data channel (above).
RESERVED_TYPES = ("signalling",)
RESERVED_PREFIX = "ping"

# What the agent is doing, for the client to show (the design's 5.5): the echo session uses
# the first three; `confirming` comes with confirmed actions.
CallState = Literal["listening", "thinking", "speaking", "confirming"]
# A reply's number in its call, from 0, as the session counts them: the greeting is reply 0.
ReplyId = Annotated[int, Field(ge=0, le=MAX_INDEX)]
# A clause's index in its reply, from 0.
ClauseIndex = Annotated[int, Field(ge=0, le=MAX_INDEX)]


def _version(value: object) -> object:
    """`value` when it is the integer itself: Python takes JSON's `true` and `1.0` as equal to
    1, and so would the literal alone."""
    if type(value) is not int:
        raise ValueError(f"must be the integer {PROTOCOL}")
    return value


class _ClientMessage(BaseModel):
    """What every client message is: parsed strictly, from a closed list, with its version."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    v: Annotated[Literal[1], BeforeValidator(_version)]


class ClientHello(_ClientMessage):
    """The client names itself and its version (`t2v-client.js/1.0.0`), once the channel opens:
    printable ASCII with no space, at most 64 characters."""

    type: Literal["hello"]
    client: str = Field(pattern=r"^[\x21-\x7e]{1,64}$")


class Stop(_ClientMessage):
    """Stop the agent's speech now: the Stop button or Esc."""

    type: Literal["stop"]


class Hangup(_ClientMessage):
    """End the call now."""

    type: Literal["hangup"]


class ClientStats(_ClientMessage, ClientConnection):
    """The browser's view of its connection (core's `ClientConnection`), sent once it connects
    and again when it learns more (the first audio played)."""

    type: Literal["client_stats"]


class Playback(_ClientMessage):
    """The browser began or finished playing one clause of the agent's reply: the clause an
    agent `caption` named by its reply and index."""

    type: Literal["playback"]
    reply_id: ReplyId
    clause: ClauseIndex
    event: Literal["started", "ended"]


class _SessionMessage(BaseModel):
    """What every session message is; the session builds it, with its version and type set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    v: Literal[1] = PROTOCOL


class SessionHello(_SessionMessage):
    """The session greets the client once the channel opens: the call's ID and the languages
    the call can be held in, the call's own first."""

    type: Literal["hello"] = "hello"
    call_id: CallId
    languages: tuple[LanguageTag, ...] = Field(min_length=1)


class State(_SessionMessage):
    """What the agent is doing now."""

    type: Literal["state"] = "state"
    state: CallState


class Caption(_SessionMessage):
    """Text to show: the caller's turn once heard (named by its `turn_id`), or the agent's reply
    clause by clause as each one plays (named by its `reply_id` and `clause`, with the caller's
    `turn_id` it answers; none for the greeting or a spoken notice). `final` is false for words
    that may still change."""

    type: Literal["caption"] = "caption"
    speaker: Literal["caller", "agent"]
    text: str
    final: bool
    turn_id: TurnId | None = None
    reply_id: ReplyId | None = None
    clause: ClauseIndex | None = None

    @model_validator(mode="after")
    def _keyed_by_its_speaker(self) -> Caption:
        agent = self.speaker == "agent"
        if agent != (self.reply_id is not None) or agent != (self.clause is not None):
            raise ValueError("an agent caption names its reply and clause, a caller's neither")
        if not agent and self.turn_id is None:
            raise ValueError("a caller's caption names its turn")
        return self


class Notice(_SessionMessage):
    """Something the caller is told, as text in the call's language: its `Language`'s notice of
    `kind` (domain/declaration.py's `NoticeKind` says when each is told)."""

    type: Literal["notice"] = "notice"
    kind: NoticeKind
    text: str = Field(min_length=1)


class Ended(_SessionMessage):
    """The call ended, and why."""

    type: Literal["ended"] = "ended"
    reason: EndReason


ClientMessage = ClientHello | Stop | Hangup | ClientStats | Playback
SessionMessage = SessionHello | State | Caption | Notice | Ended
# Every message of each direction, in the design's order.
CLIENT_MESSAGES: tuple[type[_ClientMessage], ...] = (
    ClientHello,
    Stop,
    Hangup,
    ClientStats,
    Playback,
)
SESSION_MESSAGES: tuple[type[_SessionMessage], ...] = (SessionHello, State, Caption, Notice, Ended)

_CLIENT: TypeAdapter[ClientMessage] = TypeAdapter(
    Annotated[ClientMessage, Field(discriminator="type")],
    config=ConfigDict(hide_input_in_errors=True),
)


def parse_client_message(message: object) -> ClientMessage:
    """The client's message, from the object Pipecat's transport parsed from its text, or from
    the text itself (a str or bytes). A call takes the object path: SmallWebRTC's connection
    runs `json.loads` on each data-channel message before its `on_app_message` event hands it
    on (Pipecat 1.15.0's `transports/smallwebrtc/connection.py`, lines 376-387), so the bound
    is measured on the object written back as compact JSON (UTF-8, no space), and a key the
    text held twice reaches it once, with its last value. The text path, for a transport that
    hands on the text, measures the text's own bytes and refuses a key held twice.

    InvalidRequestError for anything else: a message over MAX_CLIENT_MESSAGE_BYTES
    (`too_large`), text that is not one JSON value in UTF-8 or an object JSON cannot write
    (`json_invalid`), text holding a key twice (`duplicate_key`), or one that is not exactly one
    message of the client's (pydantic's error types). Its details name only these kinds of
    problem, never a value, a key or a type the client sent."""
    value, problem = _read(message)
    if problem is None:
        try:
            return _CLIENT.validate_python(value)
        except ValidationError as error:
            problems = {e["type"] for e in error.errors(include_input=False, include_url=False)}
    else:
        problems = {problem}
    raise _refused(problems) from None


class _KeyTwiceError(Exception):
    """A JSON object of the client's holds one key twice."""


def _once(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object's members, refusing a key held twice: `json.loads` would keep its last
    value, and a reader that took the first would see another message."""
    members = dict(pairs)
    if len(members) != len(pairs):
        raise _KeyTwiceError
    return members


def _read(message: object) -> tuple[object, str | None]:
    """`message`'s JSON value, or the kind of problem that refuses it before it is read as a
    message: its size in bytes, JSON it is not, or a key held twice."""
    if isinstance(message, str | bytes) and len(message) > MAX_CLIENT_MESSAGE_BYTES:
        return None, "too_large"  # a character is a byte or more, so its bytes are too
    try:
        if isinstance(message, str | bytes):
            text = message.encode() if isinstance(message, str) else message
            if len(text) > MAX_CLIENT_MESSAGE_BYTES:
                return None, "too_large"
            return json.loads(text.decode(), object_pairs_hook=_once), None
        written = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
    except _KeyTwiceError:
        return None, "duplicate_key"
    except (TypeError, ValueError, RecursionError):  # not UTF-8, not JSON, or not writable
        return None, "json_invalid"
    return (None, "too_large") if len(written) > MAX_CLIENT_MESSAGE_BYTES else (message, None)


def _refused(problems: Iterable[str]) -> InvalidRequestError:
    found: list[JsonValue] = []
    found.extend(sorted(problems))
    return InvalidRequestError(
        "The client sent a message that is not one of t2v/1's.", details={"problems": found}
    )


def wire(message: SessionMessage) -> dict[str, JsonValue]:
    """`message` as the JSON object the transport sends, with its version and type."""
    return message.model_dump(mode="json")
