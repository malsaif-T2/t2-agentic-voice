"""The call's current language (voice/session/call_language.py, language_moves.py): under
`stt.live_language = "detected"` a turn the detecting request heard in the agent's other language
moves the call, its record naming the language, detected, with no `ListenIn` (the bridge moved
itself); a spoken switch request moves it too, the bridge told, the talker's turn asking for it,
said over a reply as well;
the talker's `switch_language` tool (`LanguageMoved`) moves it, the bridge told after the step;
the notices and the overlap words follow the moved language. Under `session`, the library's
default (GP-18), nothing moves; and `CallLanguage`'s own rules."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from t2_agentic_voice.agent.talker import LanguageMoved
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.voice.protocol import Notice
from t2_agentic_voice.voice.session.call_language import CallLanguage
from t2_agentic_voice.voice.session.commands import ListenIn
from t2_agentic_voice.voice.session.overlap import call_words

from tests.leaks import holding, shown
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_ask_support import over_the_reply, two_clauses
from tests.t2_agentic_voice.voice.session.overlap_support import two_step
from tests.t2_agentic_voice.voice.session.session_support import (
    GAP_S,
    greeted,
    play,
    report,
    sent,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    Step,
    answer,
    settle,
    talker_call,
)

DETECTED = VoiceSettings(env="test", stt=SttSettings(live_language="detected"))
# Under hinted (D-115) on Scribe, the default provider, a turn its one answer moved is the same.
HINTED = VoiceSettings(env="test", stt=SttSettings(live_language="hinted"))
# Under single (D-117) on Scribe, too.
SINGLE = VoiceSettings(env="test", stt=SttSettings(live_language="single"))
QUESTION = "what time does my flight to Riyadh leave"
ASK_ENGLISH = "بالانجليزي لو سمحت"  # bil-ingleezi law samaht, in English please
ASK_OTHER = "ممكن نتكلم بلغة ثانية"  # mumkin nitkallam bi-lugha thanya, can we use another language
ENGLISH, ARABIC = AGENT.languages[0], AGENT.languages[1]


def _switched(_: object) -> list[Step]:
    """A reply whose `switch_language` tool moved it into English, then said a clause in it."""
    said = answer("Sure, go ahead.")
    return [*said[:2], LanguageMoved(language="en"), *said[2:]]


async def _turn(
    io: FakeSessionIO, turn_id: int, text: str | None, language: str, **given: object
) -> None:
    await io.turn_opened(turn_id)
    await io.clock.advance(2.0)
    await io.turn_closed(turn_id)
    await io.transcribing(turn_id, audio_s=2.0)
    await io.transcribed(turn_id, text, language=language, **given)  # type: ignore[arg-type]
    await settle()


@pytest.mark.parametrize(
    "settings", [DETECTED, HINTED, SINGLE], ids=["detected", "hinted", "single"]
)
def test_a_detected_turn_moves_the_call_and_the_notices_follow(settings: VoiceSettings) -> None:
    io, _, _ = talker_call(settings, language="ar-SA")

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


@pytest.mark.parametrize(
    ("text", "handed"), [("Sorry, English please", True), ("English please", False)]
)
def test_a_switch_request_said_over_a_reply_moves_the_call(text: str, handed: bool) -> None:
    """Under `two_step` (the default) speech over a reply is an overlap: a switch request said
    over one moves the call whether the rule stops the reply and hands the turn to the talker,
    or lets the reply go on for its two words; the next turn is named in English."""
    io, _, talker = talker_call(two_step(DETECTED), two_clauses, language="ar-SA")

    async def drive() -> None:
        await over_the_reply(io, text)
        await io.turn_closed(1)
        await io.transcribed(1, text, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ENGLISH
    assert io.commands.of(ListenIn) == [ListenIn(language="ar"), ListenIn(language="en")]
    asked = [turn.asked for turn in talker.turns if turn.turn_id == 1]
    assert asked == (["en"] if handed else [])


def test_the_talkers_switch_tool_moves_the_call_and_tells_the_bridge(
    caplog: pytest.LogCaptureFixture,
) -> None:
    io, _, talker = talker_call(DETECTED, _switched, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, ASK_OTHER, "ar")
        await play(io, 1)
        await settle()
        await io.clock.advance(GAP_S)
        await _turn(io, 1, None, "en", failure="timeout")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert talker.turns[0].asked is None  # no word of the list: the model's judgement
    assert io.setup.now.language == ENGLISH
    assert io.commands.of(ListenIn) == [ListenIn(language="ar"), ListenIn(language="en")]
    assert sent(io, Notice) == [Notice(kind="error", text=ENGLISH.notices["error"])]
    moved = [r for r in caplog.records if r.getMessage() == "call_language_moved"]
    assert [getattr(r, "fields", {}).get("by") for r in moved] == ["tool"]
    assert holding(ASK_OTHER, shown(caplog=caplog)) == []


def test_under_session_the_switch_tool_moves_nothing() -> None:
    io, _, _ = talker_call(VoiceSettings(env="test"), _switched, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, ASK_OTHER, "ar")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ARABIC
    assert io.commands.of(ListenIn) == [ListenIn(language="ar")]


AS_SESSION = VoiceSettings(env="test", stt=SttSettings(live_language="hinted", provider="groq"))


@pytest.mark.parametrize(
    "settings", [VoiceSettings(env="test"), AS_SESSION], ids=["session", "hinted on groq"]
)
def test_under_session_nothing_moves(settings: VoiceSettings) -> None:
    """The library's default: a switch request is a turn like any other (GP-18); and hinted on a
    provider that gives no language probability runs as session (D-115)."""
    io, _, talker = talker_call(settings, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await _turn(io, 0, ASK_ENGLISH, "ar")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.language == ARABIC
    assert io.commands.of(ListenIn) == [ListenIn(language="ar")]
    assert talker.turns[0].asked is None


def _moved_on(now: CallLanguage) -> int | None:
    return now.moved_on


def test_the_call_language_moves_only_to_another_of_the_agents() -> None:
    now = CallLanguage(ARABIC, AGENT.languages, moves=True)
    assert _moved_on(now) is None
    assert now.move("fr", on=1) is None and now.move("ar", on=1) is None
    assert now.move("ar-SA", on=1) is None
    assert now.asked("what time is it") is None
    assert now.asked_tag("English please") == "en"
    assert now.move("en", on=2) == ENGLISH and now.tag == "en" and _moved_on(now) == 2
    assert now.spoken == ["en", "ar-SA"]
    assert now.untold() == "en" and now.untold() is None  # named to the bridge once
    assert now.move("ar", on=3, told=True) == ARABIC and now.untold() is None
    fixed = CallLanguage(ARABIC, AGENT.languages, moves=False)
    assert fixed.move("en", on=1) is None and fixed.asked("English please") is None
