"""What the caller says over an action's read-back, and while it is confirming
(voice/session/read_back.py, overlap.py, interrupter.py; the owner's rulings of 2026-11-10;
docs/SECURITY.md, invariant 1): yes words, send words, fillers and listening sounds over the summary
are ignored, whatever the rule would say, the summary playing on and the words counting for nothing,
but never words with a stop or pause word (a team's added ones included, on a filler too); a stop or
pause word over the read-back stops it with no receipt, the confirming state ends, and the turn
reaches the talker with the action declined as stopped, so it asks what to change; real words over
the summary do the same, as a correction, or as a no when they are a plain no by the yes rule's
lists (D-081, amended 2026-11-11); a repeat request over it, or said whole while it is confirming,
has the session say it again, the earlier read-back void; real words over the closing question leave
the read-back to the yes rule; the client's stop and the call's end end it. The rule is the tests'
fake (overlap_support.py)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_rule import AskAgain
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    CORRECTION,
    NEW_WORDS,
    REPEAT,
    REPEAT_TEXT,
    STOP,
    FakeRule,
    two_step,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    CALLER_WORDS,
    CONSENT,
    QUESTION,
    SUMMARY_SPOKEN,
    YES_TEXT,
    asked,
    clause,
    over,
    read_whole,
    reads_back,
    receipt,
    states,
)
from tests.t2_agentic_voice.voice.session.session_support import sent, speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    FakeTalker,
    settle,
    talked,
    talker_call,
)
from tests.t2_agentic_voice.voice.session.yes_support import FakeYesRule

STOP_WORD = PRESET_WORDS["en"].stop[0]
WAIT_WORD = PRESET_WORDS["en"].wait[0]
LISTENING_WORD = PRESET_WORDS["en"].backchannel[0]
READ_BACK = [provider_text(SUMMARY_SPOKEN), QUESTION]
(FILLER,) = CONSENT.fillers
PLAIN_NO = f"no no {FILLER}"  # CONSENT's no word twice and its filler: a plain no


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it: the stop and pause words stop, and so do real words
    and, to show the session reads them first, the yes words."""
    rule.script |= {
        STOP_WORD: STOP,
        WAIT_WORD: STOP,
        CALLER_WORDS: NEW_WORDS,
        YES_TEXT: NEW_WORDS,
        REPEAT_TEXT: REPEAT,
    }
    return rule


def _call(settings: VoiceSettings) -> tuple[FakeSessionIO, Any, FakeTalker]:
    return talker_call(two_step(settings), reads_back)


@pytest.mark.parametrize("text", [YES_TEXT, LISTENING_WORD], ids=["yes", "listening"])
def test_yes_words_or_a_listening_sound_over_the_summary_are_ignored_and_it_plays_on(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], text: str
) -> None:
    """GP-08, invariant 1: a yes over the summary never stops it, never reaches the talker or
    the yes rule, and never earns a receipt for its turn; the summary plays on and the
    read-back's receipt stays for a turn begun after it."""
    io, session, talker = _call(settings)
    began: list[float] = []

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        began.append(io.clock.now())
        await over(io, 1, text)
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == []
    assert len(sent(io, Unduck)) == 1
    assert text not in rule.texts  # the session read it first
    assert [t.turn_id for t in talker.turns] == [0]
    assert [t.fate for t in session.history.turns()][1] == "went_on"
    assert session._confirming.active
    assert receipt(session, began[0]) is None  # its own turn's: never
    assert receipt(session, io.clock.now()) is not None
    assert consent[0]["code"] == "en" and consent[0]["action_send"] == ()


@pytest.mark.parametrize("part", [0, 1], ids=["over_summary", "over_question"])
@pytest.mark.parametrize("word", [STOP_WORD, WAIT_WORD], ids=["stop", "pause"])
def test_a_stop_or_pause_word_over_the_read_back_stops_it_and_the_talker_asks(
    settings: VoiceSettings,
    rule: FakeRule,
    consent: list[dict[str, Any]],
    part: int,
    word: str,
) -> None:
    """GP-08, invariant 1: a stop word over the read-back leaves no receipt; confirming ends,
    nothing is sent, and the turn, said whole, reaches the talker with the action declined, so
    it asks what to change in its own words."""
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        if part == 1:
            await clause(io, 0)
        await clause(io, part, played=False)
        await over(io, 1, word)

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None
    handed = talker.turns[1]
    assert handed.words == word and handed.cut_reply == 1
    assert handed.declined == DeclinedAction(action=ACTION, kind="stopped", words=word)
    assert states(io)[-1] != "confirming"


def test_real_words_over_the_summary_stop_it_and_reach_the_talker_declined(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """GP-08, invariant 1: an interrupted summary earns no receipt."""
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, CALLER_WORDS)

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None
    assert talker.turns[1].declined == DeclinedAction(
        action=ACTION, kind="correction", words=CALLER_WORDS
    )


def test_a_plain_no_over_the_summary_reaches_the_talker_declined_as_a_no(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """D-081 as amended 2026-11-11: words that cut the summary and are a plain no by the yes
    rule's lists (a no word, beside it only fillers) decline it as a no, not a correction."""
    rule.script[PLAIN_NO] = CORRECTION
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, PLAIN_NO)

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None
    assert talker.turns[1].declined == DeclinedAction(action=ACTION, kind="no", words=PLAIN_NO)


def test_a_stop_word_a_team_added_on_a_filler_over_the_summary_is_never_ignored(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """D-081 as amended 2026-11-11: speech holding a stop or wait word of the call's (the
    `words` settings' additions included) goes to the rule, as any stop word does, though the
    yes rule's lists hold it as a filler: it stops the summary, declined as stopped."""
    added = settings.words.model_copy(update={"stop": {"en": (FILLER,)}})
    io, session, talker = _call(settings.model_copy(update={"words": added}))
    rule.script[FILLER] = STOP

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, FILLER)

    asyncio.run(drive())
    assert FILLER in rule.texts  # the session no longer reads it first
    assert len(io.commands.of(StopSpeaking)) == 1
    assert not session._confirming.active
    assert talker.turns[1].declined == DeclinedAction(action=ACTION, kind="stopped", words=FILLER)


def test_real_words_over_the_closing_question_leave_the_read_back_to_the_yes_rule(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule
) -> None:
    """The summary played whole: words over the question stop it and reach the yes rule,
    with a receipt saying the question never ended (a yes there needs a send word); words that
    are no yes are a correction, which the talker answers."""
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0)
        await clause(io, 1, played=False)
        await over(io, 1, CALLER_WORDS)

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1
    [decided] = yes_rule.calls
    assert decided.heard.text == CALLER_WORDS
    assert decided.receipt.question_ended_at is None
    assert not session._confirming.active
    assert talker.turns[-1].declined == DeclinedAction(
        action=ACTION, kind="correction", words=CALLER_WORDS
    )


@pytest.mark.parametrize("part", [0, 1], ids=["over_summary", "over_question"])
def test_a_repeat_request_over_the_read_back_says_it_again_and_voids_the_earlier_one(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], part: int
) -> None:
    io, session, talker = _call(settings)
    found: dict[str, Any] = {}

    async def drive() -> None:
        await asked(io)
        if part == 1:
            await clause(io, 0)
        await clause(io, part, played=False)
        await over(io, 1, REPEAT_TEXT)
        found["before"] = receipt(session, io.clock.now() + 5.0)
        for index in (0, 1):
            await io.synthesizing(2, index)
            await io.clause_queued(2, index)
            await io.clock.advance(0.5)
            await io.clause_played(2, index, audio_s=2.0)
        await settle()
        found["after"] = receipt(session, io.clock.now())

    asyncio.run(drive())
    assert [s.text for s in speaks(io, 2)] == READ_BACK
    assert [t.turn_id for t in talker.turns] == [0]  # the session said it, not the talker
    assert [t.fate for t in session.history.turns()][1] == "command"
    assert found["before"] is None  # the earlier read-back's receipt is void
    assert found["after"] is not None and found["after"].reply_id == 2


def test_a_repeat_request_said_whole_while_confirming_says_the_read_back_again(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await io.clock.advance(1.0)
        await talked(io, 1, REPEAT_TEXT)

    asyncio.run(drive())
    assert [s.text for s in speaks(io, 2)] == READ_BACK
    assert [t.turn_id for t in talker.turns] == [0]
    current = session._confirming.read_back
    assert current is not None and current.reply_id == 2
    assert receipt(session, io.clock.now()) is None  # the new summary has not played


@pytest.mark.parametrize("part", [0, 1], ids=["over_summary", "over_question"])
def test_the_clients_stop_over_the_read_back_ends_it_with_no_receipt(
    settings: VoiceSettings, part: int
) -> None:
    io, session, _ = _call(settings)

    async def drive() -> None:
        await asked(io)
        if part == 1:
            await clause(io, 0)
        await clause(io, part, played=False)
        await io.client({"v": 1, "type": "stop"})

    asyncio.run(drive())
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None


def test_a_summary_clause_that_failed_ends_the_read_back_with_no_receipt(
    settings: VoiceSettings,
) -> None:
    io, session, _ = _call(settings)

    async def drive() -> None:
        await asked(io)
        await io.synthesizing(1, 0)
        await io.clause_failed(1, 0)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert not session._confirming.active
    assert receipt(session, io.clock.now() + 1.0) is None


def test_the_calls_end_ends_confirming(settings: VoiceSettings) -> None:
    io, session, _ = _call(settings)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await io.ending()

    asyncio.run(drive())
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None


@pytest.mark.parametrize("text", [STOP_WORD, REPEAT_TEXT], ids=["stop", "repeat"])
def test_over_a_line_that_asked_again_a_stop_word_declines_and_a_repeat_says_it_again(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule, text: str
) -> None:
    """A line that asked the read-back again is a follow-up of it: a stop word over it ends
    confirming, the talker hearing the turn with the action declined, and a repeat request
    over it has the read-back said again."""
    yes_rule.forced = lambda heard, receipt: AskAgain()
    io, session, talker = _call(settings)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await settle()
        await io.clock.advance(1.0)
        await talked(io, 1, "made-up mumble")
        await io.synthesizing(2, 0)
        await io.clause_queued(2, 0)  # the line that asks again plays
        await over(io, 2, text)

    asyncio.run(drive())
    assert len(yes_rule.calls) == 1  # the mumble's; nothing said over the line reached it
    if text == STOP_WORD:
        assert not session._confirming.active
        handed = talker.turns[-1]
        assert handed.turn_id == 2
        assert handed.declined == DeclinedAction(action=ACTION, kind="stopped", words=text)
    else:
        assert [s.text for s in speaks(io, 3)] == READ_BACK
        current = session._confirming.read_back
        assert current is not None and current.reply_id == 3
        assert [t.turn_id for t in talker.turns] == [0]


def test_the_clients_stop_over_a_line_that_asked_again_ends_confirming(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    yes_rule.forced = lambda heard, receipt: AskAgain()
    io, session, _ = _call(settings)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await settle()
        await io.clock.advance(1.0)
        await talked(io, 1, "made-up mumble")
        assert session._confirming.active  # asked again
        await io.synthesizing(2, 0)
        await io.clause_queued(2, 0)
        await io.client({"v": 1, "type": "stop"})

    asyncio.run(drive())
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None
