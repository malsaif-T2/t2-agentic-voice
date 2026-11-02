"""A call's events and report (the design's 6.6): frozen, from a closed list, each with its call,
its turn and its time; the report's usage per model and requests per call minute."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.events import (
    EVENTS,
    MAX_INDEX,
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ClientConnection,
    Event,
    Interrupted,
    ModelUsage,
    ProviderFailed,
    TransportFailed,
    TurnMetrics,
    TurnRecord,
    TurnTimes,
    UserTurnEnded,
)

AT = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _report(**changes: Any) -> CallReport:
    values: dict[str, Any] = {
        "call_id": "c-1",
        "agent": "branch-helper",
        "started_at": AT,
        "ended_at": AT + timedelta(minutes=3),
        "ended_by": "hangup",
    }
    return CallReport.model_validate(values | changes)


def test_the_events_are_the_closed_list_m2_emits() -> None:
    assert [e.__name__ for e in EVENTS] == [
        "CallStarted",
        "CallEnded",
        "UserTurnEnded",
        "Interrupted",
        "AgentSpeechEnded",
        "ProviderFailed",
        "TransportFailed",
        "TurnMetrics",
    ]
    assert all(issubclass(e, Event) and e.model_config.get("frozen") for e in EVENTS)
    assert all(e.model_config.get("extra") == "forbid" for e in EVENTS)


def test_every_event_carries_its_call_its_turn_and_its_time() -> None:
    started = CallStarted(call_id="c-1", at=AT)
    assert (started.call_id, started.turn_id, started.at) == ("c-1", None, AT)
    events = [
        CallEnded(call_id="c-1", at=AT, report=_report()),
        UserTurnEnded(call_id="c-1", turn_id=0, at=AT, heard=""),
        Interrupted(call_id="c-1", turn_id=1, at=AT, kind="stop"),
        AgentSpeechEnded(call_id="c-1", turn_id=1, at=AT, text="x", played_fraction=0.5),
        ProviderFailed(call_id="c-1", at=AT, kind="rate_limited", retryable=True),
        TransportFailed(call_id="c-1", at=AT, stage="connect"),
        TurnMetrics(call_id="c-1", turn_id=2, at=AT, stt_ms=310.0, ttfa_ms=900.0),
    ]
    assert [type(e) for e in [started, *events]] == list(EVENTS)
    with pytest.raises(ValidationError):
        started.at = AT  # type: ignore[misc]
    greeted = AgentSpeechEnded(call_id="c-1", at=AT, text="x", played_fraction=1.0)
    stopped = Interrupted(call_id="c-1", at=AT, kind="stop")
    assert (greeted.turn_id, stopped.turn_id) == (None, None)  # the greeting answers no turn


@pytest.mark.parametrize(
    ("event", "values"),
    [
        (UserTurnEnded, {"heard": "x"}),  # a turn's event names its turn
        (CallStarted, {"turn_id": -1}),
        (CallStarted, {"turn_id": MAX_INDEX + 1}),
        (CallStarted, {"at": datetime(2026, 11, 2, 12, 0)}),  # no time zone
        (CallStarted, {"call_id": "c 1"}),
        (CallStarted, {"call_id": "c" * 65}),
        (CallStarted, {"note": "x"}),
        (Interrupted, {"turn_id": 0, "kind": "cough"}),
        (AgentSpeechEnded, {"turn_id": 0, "text": "", "played_fraction": 1.5}),
        (ProviderFailed, {"kind": "broken", "retryable": False}),
        (TransportFailed, {"stage": "dns"}),
        (TurnMetrics, {"turn_id": 0, "stt_ms": -1.0}),
    ],
)
def test_an_event_refuses_what_is_not_in_its_list(
    event: type[Event], values: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        event.model_validate({"call_id": "c-1", "at": AT} | values)


def test_turn_metrics_are_a_turns_times() -> None:
    metrics = TurnMetrics(call_id="c-1", turn_id=2, at=AT, tts_first_audio_ms=250.0)
    times = TurnTimes.model_validate(metrics.model_dump(include=set(TurnTimes.model_fields)))
    assert times == TurnTimes(tts_first_audio_ms=250.0)
    assert times.llm_first_token_ms is None  # no talker yet


def test_a_report_counts_each_models_requests_per_call_minute() -> None:
    report = _report(
        usage=[
            ModelUsage(model="whisper-large-v3", requests=18, audio_sent_s=41.5, billed_s=180.0),
            ModelUsage(model="canopylabs/orpheus-arabic-saudi", requests=9, characters=480),
        ],
        turns=[TurnRecord(turn_id=0, language="ar-SA", heard="x", said="x")],
        client=ClientConnection(candidate_type="relay", relay_protocol="tls", turn_port=443),
        consent_version="m2-owner-test-1",
    )
    assert report.duration_s == 180.0
    assert report.requests_per_minute() == {
        "whisper-large-v3": 6.0,
        "canopylabs/orpheus-arabic-saudi": 3.0,
    }
    assert _report(
        ended_at=AT, usage=[ModelUsage(model="m", requests=1)]
    ).requests_per_minute() == {"m": 0.0}
    assert report.turns[0].times == TurnTimes()
    assert CallReport.model_validate_json(report.model_dump_json()) == report
    assert not report.turns[0].unfinished  # a turn the call ended in the middle of says so
    assert TurnRecord(turn_id=1, heard="", unfinished=True).unfinished


@pytest.mark.parametrize(
    "changes",
    [
        {"ended_at": AT - timedelta(seconds=1)},
        {"usage": [ModelUsage(model="m"), ModelUsage(model="m", requests=1)]},
        {"ended_by": "bored"},
        {"agent": ""},
    ],
)
def test_a_report_is_consistent(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _report(**changes)


def test_a_relay_alone_has_a_relay_protocol_and_a_turn_port() -> None:
    assert ClientConnection(candidate_type="relay", relay_protocol="udp").turn_port is None
    assert ClientConnection().candidate_type is None
    for bad in (
        {"candidate_type": "host", "relay_protocol": "tls"},
        {"turn_port": 443},
        {"candidate_type": "relay", "turn_port": 0},
        {"connect_ms": float("inf")},
        {"first_audio_ms": -1.0},
    ):
        with pytest.raises(ValidationError):
            ClientConnection.model_validate(bad)
