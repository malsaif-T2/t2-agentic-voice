"""The call log (flight_voice/call_log/): every call kept in the SQLite database, its setup at
its start, every event whole, each finished tool call, its turns and their times and its
recording's folder at its end; the settings that turn it off or move it; and the setup snapshot,
which holds no key."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flight_voice.airline.system import Airline
from flight_voice.call_log.compose import call_log_of, log_path
from flight_voice.call_log.log import CallLog
from flight_voice.call_log.setup import call_setup
from flight_voice.call_log.store import SCHEMA_VERSION, CallStore
from flight_voice.flight_data.compose import lean_deps
from flight_voice.lean.agent import declare
from flight_voice.voice_settings import for_the_app
from pydantic import JsonValue
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.events import (
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ToolFinished,
    TurnRecord,
    TurnTimes,
    UserTurnEnded,
)

from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.server_support import settings

CALL = "callAbc123"
AT = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
SETUP: dict[str, JsonValue] = {"agent": "flight-lean", "llm": {"model": "openai/gpt-oss-120b"}}


def _log(folder: Path) -> CallLog:
    return CallLog(CallStore(folder / "calls.sqlite3"), dict(SETUP), folder)


def _call(log: CallLog) -> None:
    """One call of a turn: heard, a tool, a reply, its end."""
    turn = TurnRecord(
        turn_id=0,
        language="ar-SA",
        heard="ودي أروح جدة",
        said="فيه 22 رحلة",
        times=TurnTimes(ttfa_ms=1800.0, stt_ms=250.0, llm_first_token_ms=900.0),
    )
    report = CallReport(
        call_id=CALL,
        agent="flight-lean",
        started_at=AT,
        ended_at=AT,
        ended_by="hangup",
        turns=(turn,),
    )
    events = [
        CallStarted(call_id=CALL, at=AT),
        UserTurnEnded(call_id=CALL, turn_id=0, at=AT, heard="ودي أروح جدة"),
        ToolFinished(
            call_id=CALL,
            turn_id=0,
            at=AT,
            tool="find_flights",
            tool_call_id="t1",
            arguments='{"destination": "Jeddah"}',
            ok=True,
            ms=2600.0,
            result='{"status": "ok"}',
        ),
        AgentSpeechEnded(call_id=CALL, turn_id=0, at=AT, text="فيه 22 رحلة", played_fraction=1.0),
        CallEnded(call_id=CALL, at=AT, report=report),
    ]

    async def play() -> None:
        for event in events:
            await log.observe(event)
        await log.aclose()

    asyncio.run(play())


def _rows(path: Path, query: str) -> list[tuple[object, ...]]:
    with sqlite3.connect(path) as db:
        return db.execute(query).fetchall()


def test_a_call_is_kept_whole_setup_events_tools_turns_and_recording(tmp_path: Path) -> None:
    (tmp_path / "recordings" / CALL).mkdir(parents=True)  # the library kept its audio
    log = _log(tmp_path)
    _call(log)
    db = tmp_path / "calls.sqlite3"
    ((setup, ended_by, turns, recording, report),) = _rows(
        db, "SELECT setup, ended_by, turns, recording, report FROM calls"
    )
    assert json.loads(str(setup)) == SETUP and ended_by == "hangup" and turns == 1
    assert recording == f"recordings/{CALL}"
    assert json.loads(str(report))["turns"][0]["heard"] == "ودي أروح جدة"
    types = [t for (t,) in _rows(db, "SELECT type FROM events ORDER BY id")]
    assert types == [
        "CallStarted",
        "UserTurnEnded",
        "ToolFinished",
        "AgentSpeechEnded",
        "CallEnded",
    ]
    ((tool, ok, ms, arguments),) = _rows(db, "SELECT tool, ok, ms, arguments FROM tool_calls")
    assert (tool, ok, ms) == ("find_flights", 1, 2600.0) and "Jeddah" in str(arguments)
    ((heard, said, ttfa, stt),) = _rows(db, "SELECT heard, said, ttfa_ms, stt_ms FROM turns")
    assert (heard, said, ttfa, stt) == ("ودي أروح جدة", "فيه 22 رحلة", 1800.0, 250.0)
    assert _rows(db, "SELECT value FROM meta") == [(str(SCHEMA_VERSION),)]


def test_a_call_with_no_recording_says_none(tmp_path: Path) -> None:
    _call(_log(tmp_path))
    assert _rows(tmp_path / "calls.sqlite3", "SELECT recording FROM calls") == [(None,)]


def test_the_setup_names_what_answered_and_holds_no_key() -> None:
    voice = for_the_app(VoiceSettings(env="test"), agent="lean", bookable=False)
    app = settings(agent="lean", flight_data="mock").app
    agent = declare(lean_deps(app, Airline(today=lambda: TODAY), app.names(), today=lambda: TODAY))
    setup = call_setup(agent, voice, app, "abc123")
    assert setup["agent"] == "flight-lean" and setup["release"] == "abc123"
    assert setup["flight_data"] == "mock" and setup["record_audio"] is True
    assert setup["tts"]["provider"] == "groq"  # type: ignore[index, call-overload]
    text = json.dumps(setup).lower()
    assert "key" not in text and "secret" not in text and "code" not in text


def test_the_log_is_on_by_default_in_the_storage_folder_and_may_be_turned_off(
    tmp_path: Path,
) -> None:
    voice = VoiceSettings.model_validate({"env": "test", "storage": {"var_dir": tmp_path}})
    app = settings().app
    assert app.call_log and log_path(app, voice) == tmp_path / "calls.sqlite3"
    agent = declare(lean_deps(app, Airline(today=lambda: TODAY), app.names(), today=lambda: TODAY))
    made = call_log_of(app, app, voice, agent)
    assert made is not None and made.store.path == tmp_path / "calls.sqlite3"
    asyncio.run(made.aclose())
    off = settings(call_log=False).app
    assert call_log_of(off, off, voice, agent) is None
    moved = settings(call_log_path=tmp_path / "elsewhere.sqlite3").app
    assert log_path(moved, voice) == tmp_path / "elsewhere.sqlite3"


@pytest.mark.parametrize("given", [{}, {"record_audio": False}])
def test_the_app_records_the_calls_audio_unless_the_environment_says_not(
    given: dict[str, bool],
) -> None:
    voice = VoiceSettings.model_validate({"env": "test", "privacy": given})
    assert for_the_app(voice).privacy.record_audio is given.get("record_audio", True)
