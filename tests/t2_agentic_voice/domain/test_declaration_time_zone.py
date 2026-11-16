"""The agent's time zone (domain/declaration.py's `VoiceAgent.time_zone`): a fixed offset from
UTC, given as a `timedelta` or a `datetime.timezone` of one, UTC unless given, in whole minutes
from -12:00 to +14:00. No zone database is installed, so a zone's name, a whole number and any
other value is refused at declaration with a ConfigurationError naming the field, with its FIX,
never the value."""

from __future__ import annotations

from datetime import UTC, timedelta, timezone
from typing import Any

import pytest
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

ENGLISH = Language.english(greeting="Hi! How can I help?")


def _agent(**fields: Any) -> VoiceAgent:
    return VoiceAgent(name="zoned", languages=[ENGLISH], **fields)


def test_an_agent_declaring_no_time_zone_keeps_utc() -> None:
    agent = _agent()
    assert agent.time_zone == timedelta(0)
    assert agent.zone == UTC


@pytest.mark.parametrize(
    ("given", "offset"),
    [
        (timedelta(hours=3), timedelta(hours=3)),
        (timezone(timedelta(hours=3)), timedelta(hours=3)),
        (timedelta(hours=5, minutes=30), timedelta(hours=5, minutes=30)),
        (timedelta(hours=-12), timedelta(hours=-12)),
        (timedelta(hours=14), timedelta(hours=14)),
        (UTC, timedelta(0)),
    ],
)
def test_a_fixed_offset_is_taken(given: object, offset: timedelta) -> None:
    agent = _agent(time_zone=given)
    assert agent.time_zone == offset
    assert agent.zone == timezone(offset)


@pytest.mark.parametrize(
    "given",
    [
        "Asia/Riyadh",
        "+03:00",
        3,
        10_800,
        3.0,
        None,
        timedelta(hours=14, minutes=1),
        timedelta(hours=-12, minutes=-1),
        timedelta(hours=3, seconds=30),
        timedelta(days=1),
    ],
)
def test_anything_but_a_fixed_offset_in_range_is_refused_naming_the_field(given: object) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        _agent(time_zone=given)
    assert raised.value.details == {"field": "time_zone"}
    assert "time_zone" in raised.value.message
    assert "Asia/Riyadh" not in raised.value.message  # the value given is never repeated


def test_a_time_zone_given_as_json_is_read_as_a_duration() -> None:
    agent = VoiceAgent.model_validate_json(
        '{"name": "zoned", "languages": [' + ENGLISH.model_dump_json() + '], "time_zone": "PT3H"}'
    )
    assert agent.time_zone == timedelta(hours=3)


def test_a_declared_time_zone_survives_its_json_and_a_bad_duration_is_refused() -> None:
    agent = _agent(time_zone=timedelta(hours=5, minutes=30))
    assert VoiceAgent.model_validate_json(agent.model_dump_json()) == agent
    with pytest.raises(ConfigurationError) as raised:
        _agent(time_zone="PT3X")
    assert raised.value.details == {"field": "time_zone"}
