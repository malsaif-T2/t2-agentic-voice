"""The `t2v/1` data-channel messages (the design's 5.5): a client's message parsed strictly and
refused, holding none of it, when it is not exactly one of the client's (the browser is not
trusted: docs/SECURITY.md's trust boundaries); the session's messages built with their version
and type; and no message named as SmallWebRTC's own (plan 003's appendix, item 13)."""

from __future__ import annotations

import json
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.core.events import MAX_INDEX, MAX_MS
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
    Ended,
    Hangup,
    Notice,
    Playback,
    SessionHello,
    SessionMessage,
    State,
    Stop,
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
    {"v": 1, "type": "playback", "turn_id": 3, "clause": 0, "event": "started"},
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
        Playback(v=1, type="playback", turn_id=3, clause=0, event="started"),
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
        {"v": 1, "type": "playback", "turn_id": "3", "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": 3.0, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": True, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": -1, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": MAX_INDEX + 1, "clause": 0, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": 3, "clause": 10**40, "event": "started"},
        {"v": 1, "type": "playback", "turn_id": 3, "clause": 0, "event": MARK},
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
        '{"v": 1, "type": "stop", "v": 2}',  # a key twice
    ],
)
def test_text_that_is_not_one_json_message_is_refused(text: str | bytes) -> None:
    assert holding(MARK, shown(_refused(text))) == []


def test_a_message_over_the_bound_is_refused_before_it_is_read() -> None:
    padded = '{"v": 1, "type": "stop"}'.ljust(MAX_CLIENT_MESSAGE_BYTES + 1)
    for text in (
        padded,
        padded.encode(),
        json.dumps({"v": 1, "type": "hello", "client": MARK * 60}),
    ):
        error = _refused(text)
        assert error.details == {"problems": ["too_large"]}
        assert holding(MARK, shown(error)) == []
    assert parse_client_message(padded[:MAX_CLIENT_MESSAGE_BYTES]) == Stop(v=1, type="stop")


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
        Notice(kind="ended", text="x"),
        Ended(reason="max_call"),
    ]
    assert [type(m) for m in messages] == list(SESSION_MESSAGES)
    sent = [wire(m) for m in messages]
    assert [(s["v"], s["type"]) for s in sent] == [(PROTOCOL, _type(t)) for t in SESSION_MESSAGES]
    assert sent[0] == {"v": 1, "type": "hello", "call_id": "c-1", "languages": ["ar-SA", "en"]}
    agent = Caption(speaker="agent", text="x", final=True, turn_id=4, clause=2)
    assert wire(agent) == {
        "v": 1,
        "type": "caption",
        "speaker": "agent",
        "text": "x",
        "final": True,
        "turn_id": 4,
        "clause": 2,
    }


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (Caption, {"speaker": "agent", "text": "x", "final": True, "turn_id": 0}),  # no clause
        (Caption, {"speaker": "caller", "text": "x", "final": True, "turn_id": 0, "clause": 0}),
        (SessionHello, {"call_id": "c-1", "languages": ()}),
        (SessionHello, {"call_id": "c-1", "languages": ("fr",)}),
        (SessionHello, {"call_id": "c 1", "languages": ("en",)}),
        (State, {"state": "napping"}),
        (Notice, {"kind": "ended", "text": ""}),
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
