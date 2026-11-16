"""A read-back whose call moved into another language before it was answered
(voice/session/read_back_moved.py, agent/read_back_language.py; D-038's amendment; docs/SECURITY.md,
invariant 1): under `stt.live_language = "detected"` a spoken switch request answering a Saudi
read-back is no answer the yes rule judges; the read-back is read again in English, from the same
draft, as the reply answering it, the old reply's receipt void, and only a yes after the new one
played whole confirms it, the draft unchanged. Under the "session" default the yes rule judges
that turn as before (GP-18). And `read_back_in`'s own rules. Every line is written for the test."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.spoken_lines import read_back_plan
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.read_back_language import read_back_in
from t2_agentic_voice.agent.talker import ReplyDone
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.voice.session.commands import ListenIn

from tests.t2_agentic_voice.actions.action_support import SUMMARY, Backend, OpenRequest, an_action
from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import receipt
from tests.t2_agentic_voice.voice.session.session_support import (
    GAP_S,
    emitted,
    greeted,
    play,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    Step,
    answer,
    settle,
    talked,
    talker_call,
)

DETECTED = VoiceSettings(env="test", stt=SttSettings(live_language="detected"))
ASK_ENGLISH = "بالانجليزي لو سمحت"  # bil-ingleezi law samaht, in English please
ACTION = an_action(Backend("answer", outbox=MemoryOutbox(), clock=FakeClock()))
ACTING = VoiceAgent(
    name="talker-test", languages=AGENT.languages, instructions="Answer briefly.", tools=[ACTION]
)
DRAFT = OpenRequest(category="software", summary=SUMMARY)
SAUDI_PLAN = read_back_plan(ACTION, DRAFT, tool_call_id="tool-call-1", tag="ar-SA")
ENGLISH_SUMMARY = f"A software request: {SUMMARY}."


def _reads_back(turn: TalkerTurn) -> list[Step]:
    if turn.turn_id == 0:
        return [ReadBackRequested(plan=SAUDI_PLAN), ReplyDone()]
    return answer("Made-up answer.")


async def _turn(io: FakeSessionIO, turn_id: int, text: str, language: str) -> None:
    await io.turn_opened(turn_id)
    await io.clock.advance(1.0)
    await io.turn_closed(turn_id)
    await io.transcribing(turn_id, audio_s=1.0)
    await io.transcribed(turn_id, text, language=language)
    await settle()


def _answers(io: FakeSessionIO) -> list[tuple[int, str]]:
    return [(e.turn_id, e.decision) for e in emitted(io, ConfirmationAnswered)]


def test_a_switch_request_has_the_read_back_read_again_in_the_new_language() -> None:
    io, session, _ = talker_call(DETECTED, _reads_back, agent=ACTING, language="ar-SA")
    late = 1_000.0  # a turn's speech long after every reply, for the receipt's check

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "ابي افتح طلب", language="ar")
        await play(io, 1)
        await io.clock.advance(GAP_S)
        assert receipt(session, late) is not None  # the Saudi read-back played whole
        await _turn(io, 1, ASK_ENGLISH, "ar")
        assert receipt(session, late) is None  # the old reply's receipt is void
        await play(io, 2)
        await io.clock.advance(GAP_S)
        made = receipt(session, late)
        assert made is not None and made.reply_id == 2
        assert made.draft_json == SAUDI_PLAN.draft_json
        await _turn(io, 2, "yes", "en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.tag == "en"
    assert io.commands.of(ListenIn) == [ListenIn(language="ar"), ListenIn(language="en")]
    again = speaks(io, 2)
    english = read_back_in(ACTING, SAUDI_PLAN, "en")
    assert english is not None and english.summary.text == ENGLISH_SUMMARY
    assert {s.language for s in again} == {"en"} and again[0].text.startswith("A software request")
    assert {s.turn_id for s in again} == {1}
    assert _answers(io) == [(2, "yes")]  # turn 1 was no answer the yes rule judged


def test_under_session_the_yes_rule_judges_that_turn() -> None:
    """The library's default: the call never moves, so nothing is read again (GP-18)."""
    settings = VoiceSettings(env="test")
    io, _, _ = talker_call(settings, _reads_back, agent=ACTING, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "ابي افتح طلب", language="ar")
        await play(io, 1)
        await io.clock.advance(GAP_S)
        await _turn(io, 1, ASK_ENGLISH, "ar")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.setup.now.tag == "ar-SA"
    assert _answers(io) == [(1, "correction")]  # the talker answers it, nothing read again
    assert [s.text for s in speaks(io) if s.turn_id == 1] == ["Made-up answer."]


def test_read_back_in_renders_the_same_draft_in_another_language() -> None:
    english = read_back_in(ACTING, SAUDI_PLAN, "en")
    assert english is not None
    assert (english.language, english.summary.text) == ("en", ENGLISH_SUMMARY)
    assert english.draft_json == SAUDI_PLAN.draft_json
    assert (english.action, english.tool_call_id) == (SAUDI_PLAN.action, "tool-call-1")


def test_read_back_in_gives_none_for_an_unknown_action_or_a_draft_that_no_longer_parses() -> None:
    assert read_back_in(AGENT, SAUDI_PLAN, "en") is None  # an agent with no such action
    broken = SAUDI_PLAN.model_copy(update={"draft_json": '{"category": "made-up"}'})
    assert read_back_in(ACTING, broken, "en") is None
