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
agent's by the session, from 0, the greeting reply 0 (`ReplyId`; session/io.py's replies),
spoken clause by clause (`ClauseIndex`). An agent's caption and a client's
`playback` report name a clause by its reply and its index, so the greeting's first clause and
a turn's echo never share a key.

SmallWebRTC, which carries the messages, keeps two names for itself (Pipecat 1.15.0's
`pipecat/transports/smallwebrtc/connection.py`, lines 82 and 376-380; plan 003's appendix, item 13):
a message typed `signalling` is its own, and raw text starting with `ping` its keep-alive. Every
`t2v/1` message is a JSON object with a `type`, and none has either name.

Plain pydantic with no Pipecat: the session (`voice/session/`, which imports no Pipecat) parses
and builds them, and Pipecat's transport only carries them, inbound through its `on_app_message`
event, outbound as urgent transport messages, so a stop never drops one (the appendix, item 8).

While the caller speaks over a reply, the session lowers the agent's voice in the browser
(`Duck`) and brings it back once the overlap is decided, whether the reply goes on or was
stopped (`Unduck`): the first step of the two-step interruption (the design's 5.5; plan 005).
A clause a stop cut while it played is captioned again, marked `cut`. A tool may show a `card`
as an extra for a client with a screen; what the caller needs is always said (D-075).
"""

from __future__ import annotations

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

from t2_agentic_voice.core.events import CallId, ClientConnection, EndReason, TurnId
from t2_agentic_voice.core.events import ClauseIndex as ClauseIndex
from t2_agentic_voice.core.events import ReplyId as ReplyId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card, CardRow, CardSlot
from t2_agentic_voice.domain.declaration import NoticeKind
from t2_agentic_voice.voice.protocol_read import read_json, refused

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
# the first three, `thinking` while a reply asked for has no audio yet, which a talker's reply
# is while the talker or a tool works (plan 006); `confirming` while an action's read-back is
# current and no reply plays (plan 007).
CallState = Literal["listening", "thinking", "speaking", "confirming"]
# A reply's number (`ReplyId`) and a clause's index in it (`ClauseIndex`) are core's
# (core/events.py), which the talker's view of the call (core/conversation.py) shares.


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
    that may still change; `cut` is true for an agent's clause a stop cut while it played, sent
    again with the mark, which the client shows as cut (a caller's caption is never cut)."""

    type: Literal["caption"] = "caption"
    speaker: Literal["caller", "agent"]
    text: str
    final: bool
    turn_id: TurnId | None = None
    reply_id: ReplyId | None = None
    clause: ClauseIndex | None = None
    cut: bool = False

    @model_validator(mode="after")
    def _keyed_by_its_speaker(self) -> Caption:
        agent = self.speaker == "agent"
        if agent != (self.reply_id is not None) or agent != (self.clause is not None):
            raise ValueError("an agent caption names its reply and clause, a caller's neither")
        if not agent and self.turn_id is None:
            raise ValueError("a caller's caption names its turn")
        if not agent and self.cut:
            raise ValueError("only an agent's caption is cut")
        return self


class ShowCard(_SessionMessage):
    """Show the caller a card: a `title`, its `steps` and its option `rows`, in order, with the
    `source` they come from when there is one (a knowledge passage's document), and the `slot`
    it names on the page when it names one (D-110). A reply says the short answer aloud, and the
    card holds the whole, which the client shows beside the captions (plan 006). Its text passed
    the output guard, as a clause's does; each row is bounded as `Card`'s are, its `mark` from
    their closed set, and its slot has `Card`'s closed shape."""

    type: Literal["card"] = "card"
    title: str = Field(min_length=1)
    steps: tuple[str, ...] = ()
    rows: tuple[CardRow, ...] = ()
    source: str | None = None
    slot: CardSlot | None = None

    @classmethod
    def of(cls, card: Card) -> ShowCard:
        return cls(
            title=card.title, steps=card.steps, rows=card.rows, source=card.source, slot=card.slot
        )


class Duck(_SessionMessage):
    """Lower the agent's playback to `level` of its volume, from 0 (silent) to 1 (as it was), at
    once: the caller is speaking over a reply, and the session is deciding whether it is an
    interruption (`interruptions.duck_level`). Every `duck` ends with exactly one `unduck` once
    its overlap is decided, whatever the verdict; one the call's end cuts gets none, and the
    client restores the volume when the call ends."""

    type: Literal["duck"] = "duck"
    level: float = Field(ge=0, le=1, allow_inf_nan=False)


class Unduck(_SessionMessage):
    """Bring the agent's playback back to its full volume: the overlap a `duck` lowered it for
    was decided, whether the reply goes on or was stopped (then sent right after the stop), so
    the next reply plays at full volume."""

    type: Literal["unduck"] = "unduck"


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
SessionMessage = SessionHello | State | Caption | ShowCard | Duck | Unduck | Notice | Ended
# Every message of each direction, in the design's order.
CLIENT_MESSAGES: tuple[type[_ClientMessage], ...] = (
    ClientHello,
    Stop,
    Hangup,
    ClientStats,
    Playback,
)
SESSION_MESSAGES: tuple[type[_SessionMessage], ...] = (
    SessionHello,
    State,
    Caption,
    ShowCard,
    Duck,
    Unduck,
    Notice,
    Ended,
)

_CLIENT: TypeAdapter[ClientMessage] = TypeAdapter(
    Annotated[ClientMessage, Field(discriminator="type")],
    config=ConfigDict(hide_input_in_errors=True),
)


def parse_client_message(message: object) -> ClientMessage:
    """The client's message, from the object Pipecat's transport parsed from its text, or from the
    text itself (a str or bytes). A call takes the object path: SmallWebRTC's connection runs
    `json.loads` on each data-channel message before its `on_app_message` event hands it on (Pipecat
    1.15.0's `pipecat/transports/smallwebrtc/connection.py`, lines 376-387), so the bound is
    measured on the object written back as compact JSON (UTF-8, no space), and a key the text held
    twice reaches it once, with its last value. The text path, for a transport that hands on the
    text, measures the text's own bytes and refuses a key held twice.

    InvalidRequestError for anything else: a message over MAX_CLIENT_MESSAGE_BYTES
    (`too_large`), text that is not one JSON value in UTF-8 or an object JSON cannot write
    (`json_invalid`), text holding a key twice (`duplicate_key`), or one that is not exactly one
    message of the client's (pydantic's error types). Its details name only these kinds of
    problem, never a value, a key or a type the client sent."""
    value, problem = read_json(message, limit=MAX_CLIENT_MESSAGE_BYTES)
    if problem is None:
        try:
            return _CLIENT.validate_python(value)
        except ValidationError as error:
            problems = {e["type"] for e in error.errors(include_input=False, include_url=False)}
    else:
        problems = {problem}
    raise refused(problems) from None


def wire(message: SessionMessage) -> dict[str, JsonValue]:
    """`message` as the JSON object the transport sends, with its version and type."""
    return message.model_dump(mode="json")
