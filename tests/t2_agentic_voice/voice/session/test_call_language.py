"""The call's current language (voice/session/call_language.py, language_moves.py): under
`stt.live_language = "detected"` a turn the detecting request heard in the agent's other language
moves the call, its record naming the language, detected, with no `ListenIn` (the bridge moved
itself); a spoken switch request moves it too, the bridge told, the talker's turn asking for it;
the notices and the overlap words follow the moved language. Under `session`, the library's
default (GP-18), nothing moves; and `CallLanguage`'s own rules."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.voice.protocol import Notice
from t2_agentic_voice.voice.session.call_language import CallLanguage
from t2_agentic_voice.voice.session.commands import ListenIn
from t2_agentic_voice.voice.session.overlap import call_words

from tests.leaks import holding, shown
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import (
    GAP_S,
    greeted,
    play,
    report,
    sent,
)
from tests.t2_agentic_voice.voice.session.talker_support import AGENT, settle, talker_call

DETECTED = VoiceSettings(env="test", stt=SttSettings(live_language="detected"))
QUESTION = "what time does my flight to Riyadh leave"
ASK_ENGLISH = "بالانجليزي لو سمحت"  # bil-ingleezi law samaht, in English please
ENGLISH, ARABIC = AGENT.languages[0], AGENT.languages[1]


async def _turn(
    io: FakeSessionIO, turn_id: int, text: str | None, language: str, **given: object
) -> None:
    await io.turn_opened(turn_id)
    await io.clock.advance(2.0)
    await io.turn_closed(turn_id)
    await io.transcribing(turn_id, audio_s=2.0)
    await io.transcribed(turn_id, text, language=language, **given)  # type: ignore[arg-type]
    await settle()


def test_a_detected_turn_moves_the_call_and_the_notices_follow() -> None:
    io, _, _ = talker_call(DETECTED, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, QUESTION, "en", switched=True)
        await play(io, 1)
        await settle()
        await io.clock.advance(GAP_S)
        await _turn(io, 1, None, "en", failure="timeout")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ENGLISH
    assert io.commands.of(ListenIn) == [ListenIn(language="ar")]  # the bridge moved itself
    first = report(io).turns[0]
    assert (first.language, first.language_by) == ("en", "detected")
    assert sent(io, Notice) == [Notice(kind="error", text=ENGLISH.notices["error"])]


def test_a_spoken_switch_request_moves_the_call_and_its_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    io, _, talker = talker_call(DETECTED, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, ASK_ENGLISH, "ar")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ENGLISH
    assert io.commands.of(ListenIn) == [ListenIn(language="ar"), ListenIn(language="en")]
    assert talker.turns[0].asked == "en"
    english = dataclasses.replace(io.setup, language=ENGLISH)
    assert call_words(io.setup) == call_words(english)  # the overlap words follow
    moved = [r for r in caplog.records if r.getMessage() == "call_language_moved"]
    assert len(moved) == 1
    assert holding(ASK_ENGLISH, shown(caplog=caplog)) == []


def test_under_session_nothing_moves() -> None:
    """The library's default: a switch request is a turn like any other (GP-18)."""
    io, _, talker = talker_call(VoiceSettings(env="test"), language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, ASK_ENGLISH, "ar")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ARABIC
    assert io.commands.of(ListenIn) == [ListenIn(language="ar")]
    assert talker.turns[0].asked is None


def test_the_call_language_moves_only_to_another_of_the_agents() -> None:
    now = CallLanguage(ARABIC, AGENT.languages, moves=True)
    assert now.move("fr") is None and now.move("ar") is None and now.move("ar-SA") is None
    assert now.asked("what time is it") is None
    assert now.asked_tag("English please") == "en"
    assert now.move("en") == ENGLISH and now.tag == "en"
    assert now.spoken == ["en", "ar-SA"]
    fixed = CallLanguage(ARABIC, AGENT.languages, moves=False)
    assert fixed.move("en") is None and fixed.asked("English please") is None
