"""The call's date (D-101): the prompt's "Today is" is the call's day in the agent's time zone
(`VoiceAgent.time_zone`, a fixed offset, UTC unless given), read from the call's clock; a text
call (`TextCall(today=...)`) and a replay (`AudioCall(today=...)`) run on a pinned day, their
clock moved by whole days so every time of day stays as it was (core/clock.py's `DatedClock`).
Without `today`, a text call's day stays its virtual clock's, 2026-01-01, and an agent declaring
no time zone keeps UTC's date."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, DatedClock, day_shift
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.evals import AudioCall, ScriptedLLM
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_parts import DatedVirtualClock, text_clock
from t2_agentic_voice.testing.text_side import VIRTUAL_START, VirtualClock

from tests.t2_agentic_voice.agent.chat_support import FakeChat, reply, said, talker
from tests.t2_agentic_voice.agent.chat_support import agent as declared
from tests.t2_agentic_voice.fakes import FakeClock, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.testing.feed_support import FakeFeed
from tests.t2_agentic_voice.testing.text_call_support import AGENT

RIYADH = timedelta(hours=3)
PINNED = date(2026, 11, 16)  # a Monday
TURN_WORDS = "How do I reset my password?"


def _prompt_date(time_zone: timedelta, *, seconds: float) -> str:
    """The date the talker's prompt says, `seconds` after the fake clock's 2026-11-02 09:00 UTC,
    for an agent in `time_zone`."""
    clock = FakeClock()
    asyncio.run(clock.advance(seconds))
    model = FakeChat(said("Sure."))
    agent = declared().model_copy(update={"time_zone": time_zone})
    turn = TalkerTurn(turn_id=1, words=TURN_WORDS, language="en")
    reply(talker(model, clock=clock, declared=agent), turn)
    prompt = model.requests[0].messages[0].content
    return prompt.split("Today is ", 1)[1].split(".", 1)[0]


def test_riyadhs_date_after_21_utc_is_the_next_day() -> None:
    at_21_30 = 12.5 * 3600  # 21:30 UTC, 00:30 in Riyadh
    assert _prompt_date(RIYADH, seconds=at_21_30) == "2026-11-03"
    assert _prompt_date(timedelta(0), seconds=at_21_30) == "2026-11-02"  # the default, UTC
    assert _prompt_date(RIYADH, seconds=at_21_30 - 3600) == "2026-11-02"  # 23:30 in Riyadh
    assert _prompt_date(-timedelta(hours=10), seconds=0) == "2026-11-01"  # 23:00 the day before
    assert _prompt_date(timedelta(hours=5, minutes=30), seconds=12.5 * 3600 - 1800) == "2026-11-03"


def test_a_dated_clock_keeps_its_time_of_day_and_its_inners_now_and_sleep() -> None:
    inner = FakeClock()
    dated = DatedClock(inner, PINNED, UTC)
    assert dated.wall() == datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
    assert dated.now() == inner.now()
    asyncio.run(inner.advance(3600))
    assert dated.wall() == datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    late = datetime(2026, 11, 15, 22, 0, tzinfo=UTC)  # 01:00 the 16th in Riyadh
    assert day_shift(late, PINNED, UTC) == timedelta(days=1)
    assert day_shift(late, PINNED, timezone(RIYADH)) == timedelta(0)
    assert (
        DatedClock(SYSTEM_CLOCK, PINNED, timezone(RIYADH))
        .wall()
        .astimezone(timezone(RIYADH))
        .date()
        == PINNED
    )


def test_a_text_calls_clock_is_virtual_and_on_the_pinned_day_when_given() -> None:
    zone = timezone(RIYADH)
    assert type(text_clock(True, None, zone)) is VirtualClock
    pinned = text_clock(True, PINNED, zone)
    assert isinstance(pinned, DatedVirtualClock)  # still moved only by its `advance`
    assert pinned.wall().astimezone(zone) == datetime(2026, 11, 16, 12, 0, tzinfo=zone)
    assert pinned.wall().time() == VIRTUAL_START.time()
    assert text_clock(False, None, zone) is SYSTEM_CLOCK
    assert text_clock(False, PINNED, zone).wall().astimezone(zone).date() == PINNED


def _text_call_date(today: date | None, time_zone: timedelta) -> str:
    llm = ScriptedLLM([list(ScriptedLLM.reply("Sure."))])
    agent = AGENT.model_copy(update={"time_zone": time_zone})

    async def scene() -> None:
        async with TextCall(agent, llm=llm, language="en", today=today) as call:
            (await call.user("Hello?")).expect.said(contains="Sure")

    asyncio.run(scene())
    prompt = llm.requests[0].messages[0].content
    return prompt.split("Today is ", 1)[1].split(".", 1)[0]


@pytest.mark.parametrize("time_zone", [timedelta(0), RIYADH, -timedelta(hours=12)])
def test_a_text_calls_prompt_says_the_pinned_day(time_zone: timedelta) -> None:
    assert _text_call_date(PINNED, time_zone) == "2026-11-16"


def test_a_text_call_with_no_day_keeps_its_virtual_day() -> None:
    assert _text_call_date(None, timedelta(0)) == "2026-01-01"
    assert _text_call_date(None, RIYADH) == "2026-01-01"  # 12:00 there


def test_a_replays_calls_run_on_the_pinned_day_when_given(
    monkeypatch: pytest.MonkeyPatch, settings: VoiceSettings
) -> None:
    feed = FakeFeed([])
    monkeypatch.setattr(audio_call, "VoiceCalls", feed.voice_calls)
    stt, tts = FakeSpeechToText(), FakeTextToSpeech()

    async def built(today: date | None) -> object:
        replay = AudioCall(settings=settings, stt=stt, tts=tts, today=today)
        await replay.start()
        await replay.aclose()
        return feed.built[-1].built["clock"]

    assert asyncio.run(built(None)) is SYSTEM_CLOCK
    dated = asyncio.run(built(PINNED))
    assert isinstance(dated, DatedClock)
    assert dated.wall().date() == PINNED  # the replay's own agent keeps UTC
