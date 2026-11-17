"""The agent the flight app serves, chosen by its setting (`FLIGHT_VOICE_AGENT`, settings.py;
server.py's `make_app`): the scripted agent by default, the lean one (D-113) when it says so,
the lean agent's settings path (the guard's rules and four requests a turn on, no yes held over
a read-back it has none of, a bare yes over its closing question answered once the reply ends:
D-116, unless the environment sets it), and its booking check observing each call's events
beside the trip book's end of call; its airline keeping the day its calendar was written for,
and a call on a stale calendar logged. The runtime is a fake that keeps what it was given."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import pytest
from fastapi import APIRouter
from flight_voice import server, settings
from flight_voice.agent import NAME
from flight_voice.airline.system import Airline
from flight_voice.booking.lines import SEND_WORDS
from flight_voice.lean.agent import NAME as LEAN
from flight_voice.lean.agent import calendar_watch
from flight_voice.settings import AGENTS, for_the_app, load
from t2_agentic_voice import ConfigurationError, VoiceSettings
from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, CallStarted, UserTurnEnded


class _Runtime:
    """A runtime that keeps what it was built with and the observers it was given."""

    built: ClassVar[list[_Runtime]] = []

    def __init__(self, agent: Any, *, settings: VoiceSettings, identity: Any) -> None:
        self.agent, self.settings = agent, settings
        self.observers: list[tuple[type, Any]] = []
        _Runtime.built.append(self)

    def on(self, kind: type) -> Any:
        def register(observer: Any) -> Any:
            self.observers.append((kind, observer))
            return observer

        return register

    def router(self) -> APIRouter:
        return APIRouter()


def _served(environment: pytest.MonkeyPatch) -> _Runtime:
    environment.setattr(server, "VoiceRuntime", _Runtime)
    server.make_app(load())
    return _Runtime.built[-1]


def test_the_scripted_agent_is_served_unless_the_setting_says_lean(
    environment: pytest.MonkeyPatch,
) -> None:
    assert AGENTS == ("scripted", "lean")
    runtime = _served(environment)
    assert runtime.agent.name == NAME and load().app.agent == "scripted"
    assert [kind for kind, _ in runtime.observers] == [CallEnded]


def test_the_lean_agent_is_served_with_its_check_observing_each_call(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    runtime = _served(environment)
    assert runtime.agent.name == LEAN
    names = [t.name for t in runtime.agent.tools]
    assert names == ["find_flights", "choose_flights", "book_trip", "traveler_profile"]
    kinds = [kind for kind, _ in runtime.observers]
    assert kinds == [CallEnded, AgentSpeechEnded, UserTurnEnded, CallEnded, CallStarted]
    checks = {observer.__self__ for _, observer in runtime.observers[1:4]}
    assert len(checks) == 1  # one booking check for every call


def test_the_lean_airline_keeps_the_day_its_calendar_was_written_for(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    riyadh = {"today": date(2026, 11, 17)}
    environment.setattr(settings, "live_today", lambda: riyadh["today"])
    airlines: list[Airline] = []
    build = server.build_app

    def kept(*args: Any, **kwargs: Any) -> Any:
        airlines.append(kwargs["airline"])
        return build(*args, **kwargs)

    environment.setattr(server, "build_app", kept)
    runtime = _served(environment)
    riyadh["today"] = date(2026, 11, 18)  # the server left running past midnight
    (airline,) = airlines
    assert airline.today() == date(2026, 11, 17)
    assert "Today is Tuesday 17 November 2026 (2026-11-17)." in runtime.agent.instructions["en"]


def test_a_call_on_a_stale_calendar_logs_it(caplog: pytest.LogCaptureFixture) -> None:
    riyadh = {"today": date(2026, 11, 17)}
    watch = calendar_watch(date(2026, 11, 17), now=lambda: riyadh["today"])
    started = CallStarted(call_id="c-1", at=datetime(2026, 11, 17, 21, tzinfo=UTC))
    caplog.set_level("ERROR")

    async def call() -> None:
        await watch(started)

    asyncio.run(call())
    assert [r for r in caplog.records if r.getMessage() == "lean_calendar_stale"] == []
    riyadh["today"] = date(2026, 11, 18)
    asyncio.run(call())
    [record] = [r for r in caplog.records if r.getMessage() == "lean_calendar_stale"]
    assert vars(record)["fields"] == {"calendar": "2026-11-17", "riyadh": "2026-11-18"}


def test_the_lean_settings_path_answers_a_yes_over_the_question_not_over_a_read_back(
    environment: pytest.MonkeyPatch,
) -> None:
    assert settings.YES_OVER_QUESTION == "answer_yes_over_question"
    assert not VoiceSettings(env="test").interruptions.answer_yes_over_question
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    voice = load().voice
    guard = voice.guard
    assert guard.plain_speech and guard.drop_stage_notes and guard.question_stop_drops_calls
    assert voice.llm.max_requests_per_turn == 4
    assert not voice.interruptions.yes_over_read_back
    assert voice.interruptions.answer_yes_over_question
    environment.setenv("T2V_INTERRUPTIONS__ANSWER_YES_OVER_QUESTION", "false")
    assert not load().voice.interruptions.answer_yes_over_question
    scripted = for_the_app(VoiceSettings(env="test"))
    assert scripted.interruptions.yes_over_read_back
    assert not scripted.interruptions.answer_yes_over_question  # the scripted agent's as it was
    lean = for_the_app(VoiceSettings(env="test"), agent="lean")
    assert not lean.interruptions.yes_over_read_back and lean.guard.plain_speech
    assert lean.interruptions.answer_yes_over_question


def test_the_lean_agent_reads_the_bookings_send_words_unless_the_environment_sets_them(
    environment: pytest.MonkeyPatch,
) -> None:
    assert VoiceSettings(env="test").words.send == {}
    assert for_the_app(VoiceSettings(env="test")).words.send == {}  # the scripted agent's own
    lean = for_the_app(VoiceSettings(env="test"), agent="lean").words.send
    assert {code: list(words) for code, words in lean.items()} == SEND_WORDS
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    environment.setenv("T2V_WORDS__SEND", '{"en": ["go on then"]}')
    assert load().voice.words.send == {"en": ("go on then",)}


def test_another_agent_is_refused_naming_its_setting(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "clever")
    with pytest.raises(ConfigurationError, match="FLIGHT_VOICE_AGENT"):
        load()
