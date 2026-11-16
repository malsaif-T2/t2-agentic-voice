"""A long read-back found by `TextCall` when its numbers are said in the caller's register, and
its key combinations as their keys (`tts.spoken_numbers` and `tts.spoken_key_combinations`;
testing/text_read_back.py's `forms`): the session says a line too long for one request in
several, each captioned as said, so the call finds the summary in those forms, the yes rule's
check reports nothing on a summary that played whole, and the read-back's expectation holds."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_parts import MAX_CHARS
from t2_agentic_voice.testing.text_read_back import readings
from t2_agentic_voice.testing.text_watch import plans_of

from tests.t2_agentic_voice.testing.action_call_support import (
    ENGLISH,
    ROOM,
    SAUDI,
    SETTLE_S,
    Backend,
    Words,
    agent_of,
    call_action,
    model,
)

# "al-mukayyif kharbaan 7777 saa'a wa 8878 riyaal wa 9797 marra, qabl 21:45 yawm 2026-12-17":
# the air conditioner has been broken 7777 hours, 8878 riyals and 9797 times, before 21:45 on
# 2026-12-17.
SAUDI_NOTE = "المكيف خربان 7777 ساعة و8878 ريال و9797 مرة، قبل 21:45 يوم 2026-12-17"
ENGLISH_NOTE = "press Ctrl + Shift + R, 2450 errors and 1375 riyals, by 14:30 on 2026-12-17"
CASES = [(SAUDI, SAUDI_NOTE, False), (ENGLISH, ENGLISH_NOTE, True)]


def _settings(*, keys: bool) -> VoiceSettings:
    tts = TtsSettings(spoken_numbers="by_register", spoken_key_combinations=keys)
    return VoiceSettings(env="test", tts=tts)


@pytest.mark.parametrize(("words", "note", "keys"), CASES, ids=["ar-SA", "en_keys"])
def test_a_long_read_back_said_by_register_is_found_and_breaks_no_rule(
    words: Words, note: str, keys: bool
) -> None:
    yes_send = f"{words.yes} {words.send}"
    llm = model({words.request: call_action(note)})

    async def scene() -> tuple[int, int, tuple[str, ...]]:
        agent, settings = agent_of(Backend()), _settings(keys=keys)
        async with TextCall(agent, llm=llm, language=words.tag, settings=settings) as call:
            asked = await call.user(words.request)
            await call.advance(SETTLE_S)
            asked.expect.read_back(contains=ROOM, room=ROOM, note=note)
            sent = await call.user(yes_send)
            await call.advance(SETTLE_S)
            sent.expect.confirmed("book_visit", room=ROOM, note=note)
            _, session = call._parts()
            (plan,) = plans_of(call._watched)
            (reading,) = readings(session.playback, [plan])
            return len(reading.summary), len(plan.summary.spoken), call.violations

    clauses, length, violations = asyncio.run(scene())
    assert clauses > 1 and length > MAX_CHARS // 2  # said in several requests
    assert violations == ()
