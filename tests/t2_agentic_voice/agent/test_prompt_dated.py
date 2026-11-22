"""Instructions written for a day (`Dated`, domain/talker_declaration.py; agent/prompt.py's
`compose_prompt`, D-135): the library asks for them as it composes each prompt, with the
prompt's date and the reply's tag, so a server left running past midnight prompts with the new
day; a text or a text per tag reads as before, and a value that is none of them is refused."""

from __future__ import annotations

from datetime import date

import pytest
from t2_agentic_voice.agent.prompt import compose_prompt
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import VoiceAgent

from tests.t2_agentic_voice.agent.chat_support import ENGLISH, SAUDI


def test_dated_instructions_are_written_for_each_prompts_day_and_tag() -> None:
    asked: list[tuple[date, str]] = []

    def written(day: date, tag: str) -> str:
        asked.append((day, tag))
        return f"The plan for {day.isoformat()} in {tag}."

    agent = VoiceAgent(name="day-helper", languages=[SAUDI, ENGLISH], instructions=written)
    assert agent.instructed
    first = compose_prompt(agent, language="en", today=date(2026, 11, 19))
    later = compose_prompt(agent, language="ar-SA", today=date(2026, 11, 22))
    assert "The plan for 2026-11-19 in en." in first and "Today is 2026-11-19." in first
    assert "The plan for 2026-11-22 in ar-SA." in later and "Today is 2026-11-22." in later
    assert asked == [(date(2026, 11, 19), "en"), (date(2026, 11, 22), "ar-SA")]


def test_a_text_or_a_text_per_tag_reads_as_before() -> None:
    one = VoiceAgent(name="day-helper", languages=[ENGLISH], instructions="Answer briefly.")
    assert "Answer briefly." in compose_prompt(one, language="en", today=date(2026, 11, 22))
    each = VoiceAgent(
        name="day-helper",
        languages=[SAUDI, ENGLISH],
        instructions={"ar-SA": "جاوب باختصار.", "en": "Answer briefly."},
    )
    assert "جاوب باختصار." in compose_prompt(each, language="ar-SA", today=date(2026, 11, 22))


def test_instructions_that_are_no_text_mapping_or_function_are_refused() -> None:
    with pytest.raises(ConfigurationError, match="FIX: "):
        VoiceAgent(name="day-helper", languages=[ENGLISH], instructions=42)  # type: ignore[arg-type]
