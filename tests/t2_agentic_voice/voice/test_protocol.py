"""The `t2v/1` data-channel messages (the design's 5.5): a client's message parsed strictly and
refused, holding none of it, when it is not exactly one of the client's (the browser is not
trusted: docs/SECURITY.md's trust boundaries), its size counted in bytes on both paths and a key
held twice refused in its text, the object path taking what Pipecat's parse left (no padding, a
key's last value); the session's messages built with their version and type, an agent's caption
keyed on its reply and only an agent's marked cut, `duck`'s level from 0 to 1; and no message
named as SmallWebRTC's own (plan 003's appendix, item 13)."""

from __future__ import annotations

import json
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.core.events import MAX_INDEX, MAX_MS
from t2_agentic_voice.domain.cards import Card, CardRow
from t2_agentic_voice.voice.protocol import (
    CLIENT_MESSAGES,
    MAX_CLIENT_MESSAGE_BYTES,
    PROTOCOL,
    RESERVED_PREFIX,
    RESERVED_TYPES,
    SESSION_MESSAGES,
    Caption,
    ClientHello,
    ClientStats,
    Duck,
    Ended,
    Hangup,
    Notice,
    Playback,
    SessionHello,
    SessionMessage,
    ShowCard,
    State,
    Stop,
    Unduck,
    parse_client_message,
    wire,
)

from tests.leaks import holding, shown

MARK = "zx-made-up-mark-77"  # a value, a key or a type no refusal may repeat
VALID: list[dict[str, Any]] = [
    {"v": 1, "type": "hello", "client": "t2v-client.js/1.0.0"},
    {"v": 1, "type": "stop"},
    {"v": 1, "type": "hangup"},
    {"v": 1, "type": "client_stats", "candidate_type": "host", "connect_ms": 412},
    {"v": 1, "type": "playback", "reply_id": 3, "clause": 0, "event": "started"},
]


def _type(model: type[Any]) -> str:
    (name,) = get_args(model.model_fields["type"].annotation)
    return str(name)


def _refused(message: object) -> InvalidRequestError:
    with pytest.raises(InvalidRequestError) as raised:
        parse_client_message(message)
    error = raised.value
    assert error.code == "invalid_request"
    assert (error.__cause__, error.__context__) == (None, None)  # pydantic's error is in no chain
    return error


def test_each_client_message_parses_from_its_text_and_from_pipecats_object() -> None:
    expected = [
        ClientHello(v=1, type="hello", client="t2v-client.js/1.0.0"),
        Stop(v=1, type="stop"),
        Hangup(v=1, type="hangup"),
        ClientStats(v=1, type="client_stats", candidate_type="host", connect_ms=412.0),
        Playback(v=1, type="playback", reply_id=3, clause=0, event="started"),
    ]
    assert [_type(m) for m in CLIENT_MESSAGES] == [m["type"] for m in VALID]
    for message, model in zip(VALID, expected, strict=True):
        assert parse_client_message(message) == model
        assert parse_client_message(json.dumps(message)) == model
        assert parse_client_message(json.dumps(message).encode()) == model
    relayed = {"candidate_type": "relay", "relay_protocol": "tls", "turn_port": 443}
    stats = parse_client_message(
        {"v": 1, "type": "client_stats", "echo_cancellation": True} | relayed
    )
    assert isinstance(stats, ClientStats) and (stats.turn_port, stats.echo_cancellation) == (
        443,
        True,
    )


@pytest.mark.parametrize(
    "message",
    [
        {"v": 1, "type": MARK},  # a type t2v/1 does not have
        {"v": 1, "type": "signalling", "message": {"type": "renegotiate"}},  # SmallWebRTC's own
        {"v": 1, "type": "Stop"},
        {"v": 1, "type": 7},
        {"v": 1},
        {"type": "stop"},  # no version
        {"v": 2, "type": "stop"},
        {"v": "1", "type": "stop"},
        {"v": True, "type": "stop"},
        {"v": 1.0, "type": "stop"},
        {"v": None, "type": "stop"},
        {"v": 1, "type": "stop", MARK: 1},  # a key it does not have
        {"v": 1, "type": "stop", "record_audio": True},  # no message carries consent
        {"v": 1, "type": "hangup", "subject": MARK},  # or identity
        {"v": 1, "type": "hello"},
        {"v": 1, "type": "hello", "client": ""},
        {"v": 1, "type": "hello", "client": f"{MARK} 1.0"},
        {"v": 1, "type": "hello", "client": MARK * 4},  # over 64 characters
        {"v": 1, "type": "hello", "client": f"{MARK}é"},
        {"v": 1, "type": "hello", "client": 1},
        {"v": 1, "type": "hello", "client": "x", "consent": {"record_audio": True}},
        {"v": 1, "type": "client_stats", "candidate_type": MARK},
        {"v": 1, "type": "client_stats", "candidate_type": "host", "relay_protocol": "tls"},
        {"v": 1, "type": "client_stats", "candidate_type": "host", "turn_port": 443},
        {"v": 1, "type": "client_stats", "candidate_type": "relay", "relay_protocol": MARK},
        {"v": 1, "type": "client_stats", "candidate_type": "relay", "turn_port": 0},
        {"v": 1, "type": "client_stats", "candidate_type": "relay", "turn_port": 65536},
        {"v": 1, "type": "client_stats", "candidate_type": "relay", "turn_port": "443"},
        {"v": 1, "type": "client_stats", "candidate_type": "relay", "turn_port": 443.0},
        {"v": 1, "type": "client_stats", "connect_ms": "412"},
        {"v": 1, "type": "client_stats", "connect_ms": -1},
        {"v": 1, "type": "client_stats", "connect_ms": MAX_MS + 1},
        {"v": 1, "type": "client_stats", "first_audio_ms": float("nan")},
        {"v": 1, "type": "client_stats", "echo_cancellation": 1},
        {"v": 1, "type": "client_stats", "echo_cancellation": "true"},
        {"v": 1, "type": "playback", "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": 3, "clause": 0, "event": "started"},  # a turn's
        {"v": 1, "type": "playback", "reply_id": "3", "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": 3.0, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": True, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": -1, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": MAX_INDEX + 1, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": 3, "clause": 10**40, "event": "started"},
        {"v": 1, "type": "playback", "reply_id": 3, "clause": 0, "event": MARK},
        [{"v": 1, "type": "stop"}],
        MARK,
        7,
        None,
    ],
)
def test_a_client_message_that_is_not_exactly_one_of_t2vs_is_refused_holding_none_of_it(
    message: object,
) -> None:
    for form in (message, json.dumps(message)):
        error = _refused(form)
        assert error.message == "The client sent a message that is not one of t2v/1's."
        assert holding(MARK, shown(error)) == []
        problems = error.details["problems"]
        assert isinstance(problems, list) and problems and all(isinstance(p, str) for p in problems)


@pytest.mark.parametrize(
    "text",
    [
        "ping",  # SmallWebRTC's keep-alive is no JSON, and no client sends it
        f'{{"v": 1, "type": "stop"{MARK}',
        b'{"v": 1, "type": "\xff\xfe"}',  # not UTF-8
        "\ufeff" + '{"v": 1, "type": "stop"}',  # a byte-order mark before it
        "",
    ],
)
def test_text_that_is_not_one_json_message_is_refused(text: str | bytes) -> None:
    error = _refused(text)
    assert error.details == {"problems": ["json_invalid"]}
    assert holding(MARK, shown(error)) == []


@pytest.mark.parametrize(
    "text",
    [
        '{"v": 1, "type": "stop", "v": 2}',
        '{"v": 2, "type": "stop", "v": 1}',  # its last value alone would pass
        '{"v": 1, "type": "signalling", "type": "stop"}',
        f'{{"v": 1, "type": "hello", "client": "{MARK}", "client": "t2v-client.js/1.0.0"}}',
    ],
)
def test_a_key_held_twice_in_a_messages_text_is_refused(text: str) -> None:
    """`json.loads` and pydantic keep a key's last value: the text path refuses the key twice,
    whatever its values, so no reader sees another message than the session parsed."""
    for form in (text, text.encode()):
        error = _refused(form)
        assert error.details == {"problems": ["duplicate_key"]}
        assert holding(MARK, shown(error)) == []


def test_a_key_held_twice_reaches_a_call_with_its_last_value() -> None:
    """A call's path: Pipecat's `json.loads` keeps a key's last value before the object reaches
    `parse_client_message`, so the refusal above holds on the text path alone."""
    for text in (
        '{"v": 2, "type": "stop", "v": 1}',
        '{"v": 1, "type": "signalling", "type": "stop"}',
    ):
        assert parse_client_message(json.loads(text)) == Stop(v=1, type="stop")


def test_a_message_padded_past_the_bound_reaches_a_call_within_it() -> None:
    """The bound is on the message as the session gets it: whitespace padding a stop to 60 KB
    on the data channel is gone from the object Pipecat parsed, which is within the bound, while
    the same text on the text path is refused."""
    text = '{"v": 1, "type": "stop"' + " " * 60_000 + "}"
    assert len(text.encode()) > 60_000
    assert parse_client_message(json.loads(text)) == Stop(v=1, type="stop")
    assert _refused(text).details == {"problems": ["too_large"]}


def test_a_message_over_the_bound_is_refused_before_it_is_read() -> None:
    padded = '{"v": 1, "type": "stop"}'.ljust(MAX_CLIENT_MESSAGE_BYTES + 1)
    arabic = json.dumps({"v": 1, "type": "hello", "client": "\u0628" * 500}, ensure_ascii=False)
    assert len(arabic) <= MAX_CLIENT_MESSAGE_BYTES < len(arabic.encode())  # its bytes count
    for text in (
        padded,
        padded.encode(),
        json.dumps({"v": 1, "type": "hello", "client": MARK * 60}),
        arabic,
    ):
        error = _refused(text)
        assert error.details == {"problems": ["too_large"]}
        assert holding(MARK, shown(error)) == []
    assert parse_client_message(padded[:MAX_CLIENT_MESSAGE_BYTES]) == Stop(v=1, type="stop")


def _at_length(length: int) -> dict[str, Any]:
    """A `hello` whose compact JSON, in UTF-8, is `length` bytes, its name too long to pass."""
    shell = len(json.dumps({"v": 1, "type": "hello", "client": ""}, separators=(",", ":")))
    return {"v": 1, "type": "hello", "client": "x" * (length - shell)}


def test_pipecats_object_is_bounded_as_its_compact_json_in_bytes() -> None:
    """A call's path: the object Pipecat parsed is written back as compact UTF-8 JSON and
    measured, however its text was spaced."""
    assert len(json.dumps(_at_length(1000), separators=(",", ":"))) == 1000
    at_bound = _refused(_at_length(MAX_CLIENT_MESSAGE_BYTES))  # refused for its name alone
    assert at_bound.details == {"problems": ["string_pattern_mismatch"]}
    for message in (
        _at_length(MAX_CLIENT_MESSAGE_BYTES + 1),
        {"v": 1, "type": "hello", "client": "\u0628" * 600},  # 600 characters, 1200 bytes
        {"v": 1, "type": "stop"} | {f"k{i}": i for i in range(100_000)},
    ):
        assert _refused(message).details == {"problems": ["too_large"]}


@pytest.mark.parametrize(
    "message",
    [{"v": 1, "type": "stop", "at": object()}, {"v": 1, "type": {"stop"}}, {"v": 1, "x": b"x"}],
)
def test_an_object_json_cannot_write_is_refused(message: object) -> None:
    assert _refused(message).details == {"problems": ["json_invalid"]}


def test_an_object_nested_deeper_than_json_writes_is_refused() -> None:
    nested: list[object] = []
    for _ in range(100_000):
        nested = [nested]
    assert _refused({"v": 1, "type": "stop", "x": nested}).details == {"problems": ["json_invalid"]}


def test_the_longest_valid_client_message_fits_the_bound_several_times_over() -> None:
    longest = {
        "v": 1,
        "type": "client_stats",
        "candidate_type": "relay",
        "relay_protocol": "tls",
        "turn_port": 65535,
        "connect_ms": MAX_MS - 1e-8,
        "echo_cancellation": False,
        "first_audio_ms": MAX_MS - 1e-8,
    }
    text = json.dumps(longest, separators=(", ", ": "))
    assert isinstance(parse_client_message(text), ClientStats)
    assert 3 * len(text.encode()) <= MAX_CLIENT_MESSAGE_BYTES


def test_each_session_message_goes_out_with_its_version_and_type() -> None:
    messages: list[SessionMessage] = [
        SessionHello(call_id="c-1", languages=("ar-SA", "en")),
        State(state="listening"),
        Caption(speaker="caller", text="x", final=True, turn_id=0),
        ShowCard(title="x", steps=("a", "b")),
        Duck(level=0.25),
        Unduck(),
        Notice(kind="ended", text="x"),
        Ended(reason="max_call"),
    ]
    assert [type(m) for m in messages] == list(SESSION_MESSAGES)
    sent = [wire(m) for m in messages]
    assert [(s["v"], s["type"]) for s in sent] == [(PROTOCOL, _type(t)) for t in SESSION_MESSAGES]
    assert sent[0] == {"v": 1, "type": "hello", "call_id": "c-1", "languages": ["ar-SA", "en"]}
    agent = Caption(speaker="agent", text="x", final=True, turn_id=4, reply_id=5, clause=2)
    assert wire(agent) == {
        "v": 1,
        "type": "caption",
        "speaker": "agent",
        "text": "x",
        "final": True,
        "turn_id": 4,
        "reply_id": 5,
        "clause": 2,
        "cut": False,
    }
    greeting = Caption(speaker="agent", text="x", final=True, reply_id=0, clause=0)
    assert (wire(greeting)["turn_id"], sent[2]["reply_id"], sent[2]["clause"]) == (None,) * 3
    cut = Caption(speaker="agent", text="x", final=True, reply_id=5, clause=2, cut=True)
    assert wire(cut)["cut"] is True and sent[2]["cut"] is False
    card = {"v": 1, "type": "card", "title": "x", "steps": ["a", "b"], "rows": [], "source": None}
    assert sent[3] == card | {"slot": None, "links": []}
    assert (sent[4], sent[5]) == (
        {"v": 1, "type": "duck", "level": 0.25},
        {"v": 1, "type": "unduck"},
    )


def test_a_card_goes_out_with_its_rows_as_the_tool_gave_them() -> None:
    rows = (CardRow(title="09:10 to 16:15", value="2,450 SAR", mark="best"), CardRow(title="b"))
    card = Card(title="Riyadh to London", steps=("Nonstop",), rows=rows, source="timetable")
    assert wire(ShowCard.of(card)) == {
        "v": 1,
        "type": "card",
        "title": "Riyadh to London",
        "steps": ["Nonstop"],
        "rows": [
            {"title": "09:10 to 16:15", "detail": None, "value": "2,450 SAR", "mark": "best"},
            {"title": "b", "detail": None, "value": None, "mark": None},
        ],
        "source": "timetable",
        "slot": None,
        "links": [],
    }
    assert ShowCard.of(Card(title="x")) == ShowCard(title="x")
    # A card that names its slot on the page goes out with it (D-110).
    assert wire(ShowCard.of(Card(title="x", slot="return_leg")))["slot"] == "return_leg"


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (Caption, {"speaker": "agent", "text": "x", "final": True, "turn_id": 0}),  # no reply
        (Caption, {"speaker": "agent", "text": "x", "final": True, "reply_id": 0}),  # no clause
        (Caption, {"speaker": "agent", "text": "x", "final": True, "clause": 0}),
        (Caption, {"speaker": "caller", "text": "x", "final": True, "turn_id": 0, "clause": 0}),
        (Caption, {"speaker": "caller", "text": "x", "final": True, "turn_id": 0, "reply_id": 0}),
        (Caption, {"speaker": "caller", "text": "x", "final": True}),  # no turn
        (Caption, {"speaker": "caller", "text": "x", "final": True, "turn_id": 0, "cut": True}),
        (Caption, {"speaker": "agent", "text": "x", "final": True, "reply_id": -1, "clause": 0}),
        (SessionHello, {"call_id": "c-1", "languages": ()}),
        (SessionHello, {"call_id": "c-1", "languages": ("fr",)}),
        (SessionHello, {"call_id": "c 1", "languages": ("en",)}),
        (State, {"state": "napping"}),
        (Notice, {"kind": "ended", "text": ""}),
        (ShowCard, {"title": "", "steps": ()}),
        (ShowCard, {"title": "x", "steps": "a"}),  # not a list of steps
        (ShowCard, {"title": "x", "rows": [{"title": "a", "mark": "top"}]}),  # not a mark
        (ShowCard, {"title": "x", "rows": [{"title": "a" * 81}]}),
        (ShowCard, {"title": "x", "rows": "a"}),
        (ShowCard, {"title": "x", "slot": "Outbound"}),  # not the slot's closed shape
        (ShowCard, {"title": "x", "slot": ""}),
        (Duck, {"level": 1.5}),
        (Duck, {"level": -0.1}),
        (Duck, {"level": float("nan")}),
        (Duck, {}),
        (Ended, {"reason": "bored"}),
        (State, {"state": "listening", "v": 2}),
        (State, {"state": "listening", "extra": 1}),
    ],
)
def test_the_session_builds_only_messages_t2v_has(model: type[Any], values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)


def test_no_message_is_named_as_smallwebrtcs_own() -> None:
    types = [_type(m) for m in (*CLIENT_MESSAGES, *SESSION_MESSAGES)]
    assert RESERVED_TYPES == ("signalling",) and RESERVED_PREFIX == "ping"
    assert not [t for t in types if t in RESERVED_TYPES or t.startswith(RESERVED_PREFIX)]
    assert json.dumps(wire(State(state="speaking"))).startswith("{")  # an object, never raw text
