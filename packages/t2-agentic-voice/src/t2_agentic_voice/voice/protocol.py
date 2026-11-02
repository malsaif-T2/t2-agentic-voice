"""The `t2v/1` messages on a call's data channel (the design's 5.5): what the client sends the
session, and what the session sends the client. Each is a JSON object carrying `"v": 1` and a
`type` from a closed list; the HTTP bodies that set the call up are api/protocol.py's. Provisional,
but for the version check at join.

The browser is not trusted (docs/SECURITY.md's trust boundaries), so `parse_client_message`
parses a client's message strictly: one of the client's types, with exactly its fields, each of
its JSON type (no "1" or 1.0 for an integer, no 1 for a boolean), every size bounded, and the
whole message at most MAX_CLIENT_MESSAGE_BYTES; anything else is an InvalidRequestError that
holds none of it. No client message can set the caller's identity or consent (the design's 5.5).

SmallWebRTC, which carries the messages, keeps two names for itself (Pipecat 1.15.0's
`transports/smallwebrtc/connection.py`, lines 82 and 376-380; plan 003's appendix, item 13): a
message typed `signalling` is its own, and raw text starting with `ping` its keep-alive. Every
`t2v/1` message is a JSON object with a `type`, and none has either name.

Plain pydantic with no Pipecat: the session (`voice/session/`, which imports no Pipecat) parses
and builds them, and Pipecat's transport only carries them, inbound through its `on_app_message`
event, outbound as urgent transport messages, so a stop never drops one (the appendix, item 8).
"""

from __future__ import annotations

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

# The protocol's version: every message carries it as "v", and /join checks the client's.
PROTOCOL: Final = 1
# The longest message a client sends, as JSON text (the agent's bound): the longest valid one,
# a `client_stats` with every field at its longest, fits in it several times over (a test).
MAX_CLIENT_MESSAGE_BYTES = 1024
# What SmallWebRTC keeps for itself on the data channel (above).
RESERVED_TYPES = ("signalling",)
RESERVED_PREFIX = "ping"

# What the agent is doing, for the client to show (the design's 5.5): the echo session uses
# the first three; `confirming` comes with confirmed actions.
CallState = Literal["listening", "thinking", "speaking", "confirming"]
# A notice's kind, each shown with text in the call's language: `busy` comes with admission
# control.
NoticeKind = Literal["busy", "error", "ended"]
# A clause's index in its turn's reply, from 0.
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
    agent `caption` named by its turn and index."""

    type: Literal["playback"]
    turn_id: TurnId
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
    """Text to show: the caller's turn once heard, or the agent's reply clause by clause as each
    one plays (an agent caption names its clause; a caller's names none). `final` is false for
    words that may still change."""

    type: Literal["caption"] = "caption"
    speaker: Literal["caller", "agent"]
    text: str
    final: bool
    turn_id: TurnId
    clause: ClauseIndex | None = None

    @model_validator(mode="after")
    def _clause_is_the_agents(self) -> Caption:
        if (self.speaker == "agent") != (self.clause is not None):
            raise ValueError("an agent caption names its clause, and a caller's names none")
        return self


class Notice(_SessionMessage):
    """Something the caller is told, as text in the call's language."""

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
    """The client's message, from its JSON text (a str or bytes, as the channel carried it) or
    the object Pipecat's transport parsed from that text. InvalidRequestError for anything
    else: text over MAX_CLIENT_MESSAGE_BYTES, text that is not JSON, or an object that is not
    exactly one message of the client's. Its details name only the kinds of problem found
    (pydantic's error types), never a value, a key or a type the client sent."""
    if isinstance(message, str | bytes) and len(message) > MAX_CLIENT_MESSAGE_BYTES:
        raise _refused(["too_large"])  # a str holds at least one byte a character
    try:
        if isinstance(message, str | bytes):
            return _CLIENT.validate_json(message)
        return _CLIENT.validate_python(message)
    except ValidationError as error:
        problems = {e["type"] for e in error.errors(include_input=False, include_url=False)}
    raise _refused(problems) from None


def _refused(problems: Iterable[str]) -> InvalidRequestError:
    found: list[JsonValue] = []
    found.extend(sorted(problems))
    return InvalidRequestError(
        "The client sent a message that is not one of t2v/1's.", details={"problems": found}
    )


def wire(message: SessionMessage) -> dict[str, JsonValue]:
    """`message` as the JSON object the transport sends, with its version and type."""
    return message.model_dump(mode="json")
