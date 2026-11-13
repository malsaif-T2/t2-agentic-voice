"""Each read-back's action moves through the lifecycle's table (voice/session/read_back_flow.py,
for read_back.py's `Confirming`; domain/action_flow.py): every way confirming ends or goes on is
the table's own move, so none is refused; the client's stop and the call's end, which the table
has no event for, move nothing; and a move the table refuses is logged as `action_flow_refused`,
by the call, the action, the state and the event alone, and never raised: the call goes on as it
would. The rules are the tests' fakes (overlap_support.py, yes_support.py)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.action_flow import ActionState, FlowEvent, moved
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_rule import AskAgain
from t2_agentic_voice.voice.session import read_back_flow
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.leaks import holding, shown
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    NEW_WORDS,
    REPEAT,
    REPEAT_TEXT,
    STOP,
    FakeRule,
    overlap_part,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    CALLER_WORDS,
    DRAFT,
    SUMMARY,
    asked,
    clause,
    over,
    read_whole,
)
from tests.t2_agentic_voice.voice.session.talker_support import settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    FakeJobs,
    FakeYesRule,
    confirm_call,
    play_reply,
    read_back_played,
)

REFUSED = "action_flow_refused"
STOP_WORD = PRESET_WORDS["en"].stop[0]
YES = "made-up-yes"  # a yes word alone, after the closing question
Moves = list[tuple[ActionState, FlowEvent]]


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it: a stop word stops, real words stop, and a repeat
    request repeats."""
    rule.script |= {STOP_WORD: STOP, CALLER_WORDS: NEW_WORDS, REPEAT_TEXT: REPEAT}
    return rule


@pytest.fixture
def moves(monkeypatch: pytest.MonkeyPatch) -> Moves:
    """The moves the confirming state asks of the table, each still made by it."""
    asked_of: Moves = []

    def spied(state: ActionState, event: FlowEvent) -> ActionState | None:
        asked_of.append((state, event))
        return moved(state, event)

    monkeypatch.setattr(read_back_flow, "moved", spied)
    return asked_of


@pytest.mark.parametrize(
    ("text", "event", "state"),
    [(YES, "yes", "confirmed"), ("no", "no", "declined"), (CALLER_WORDS, "correction", "declined")],
    ids=["yes", "no", "correction"],
)
def test_the_yes_rules_answer_moves_the_action_as_the_table_says(
    settings: VoiceSettings, yes_rule: FakeYesRule, moves: Moves, text: str, event: str, state: str
) -> None:
    jobs = FakeJobs()
    io, session, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, text)

    asyncio.run(drive())
    assert moves == [("confirming", event)]
    assert session._confirming.state == state
    assert len(jobs.runs) == (1 if event == "yes" else 0)


def test_an_unclear_answer_asked_again_stays_confirming_then_the_last_declines_it(
    settings: VoiceSettings, yes_rule: FakeYesRule, moves: Moves
) -> None:
    yes_rule.forced = lambda heard, receipt: AskAgain()
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await read_back_played(io)
        for turn_id in (1, 2, 3):
            await talked(io, turn_id, f"made-up mumble {turn_id}")
            await play_reply(io, turn_id + 1)
            await io.clock.advance(1.0)

    asyncio.run(drive())
    assert moves == [
        ("confirming", "asked_again"),
        ("confirming", "asked_again"),
        ("confirming", "unclear"),
    ]
    assert session._confirming.state == "declined"


def test_a_stop_request_said_whole_while_confirming_is_a_stop(
    settings: VoiceSettings, yes_rule: FakeYesRule, moves: Moves
) -> None:
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, STOP_WORD)

    asyncio.run(drive())
    assert moves == [("confirming", "stop")]
    assert session._confirming.state == "declined"


@pytest.mark.parametrize(
    ("text", "event"), [(STOP_WORD, "stop"), (CALLER_WORDS, "correction")], ids=["stop", "words"]
)
def test_a_stop_word_or_real_words_over_the_summary_decline_it(
    settings: VoiceSettings,
    rule: FakeRule,
    consent: list[dict[str, Any]],
    moves: Moves,
    text: str,
    event: str,
) -> None:
    io, session, talker = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, text)

    asyncio.run(drive())
    assert moves == [("confirming", event)]
    assert session._confirming.state == "declined"
    assert talker.turns[1].declined is not None


def test_a_repeat_request_over_the_read_back_says_it_again_still_confirming(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], moves: Moves
) -> None:
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, REPEAT_TEXT)

    asyncio.run(drive())
    assert moves == [("confirming", "repeat")]
    current = session._confirming.read_back
    assert session._confirming.state == "confirming"
    assert current is not None and current.reply_id == 2


def test_a_repeat_request_answered_instead_of_said_again_is_a_correction(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], moves: Moves
) -> None:
    """The window hears a repeat request over the summary, and the whole overlap new words: the
    turn is answered instead, the action declined as a correction, and nothing is said again."""
    io, session, talker = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await io.turn_opened(1)
        await overlap_part(io, 1, REPEAT_TEXT, part="window", audio_s=0.75)
        await overlap_part(io, 1, CALLER_WORDS)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.6)
        await io.transcribed(1, CALLER_WORDS, language="en")
        await settle()

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1  # the window's repeat request stopped it
    assert moves == [("confirming", "correction")]
    assert session._confirming.state == "declined" and session._confirming.read_back is None
    declined = talker.turns[1].declined
    assert declined is not None and declined.kind == "correction"


def test_a_repeat_request_said_whole_while_confirming_says_it_again_still_confirming(
    settings: VoiceSettings, rule: FakeRule, moves: Moves
) -> None:
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await io.clock.advance(1.0)
        await talked(io, 1, REPEAT_TEXT)

    asyncio.run(drive())
    assert moves == [("confirming", "repeat")]
    assert session._confirming.state == "confirming"


def test_a_turn_begun_in_the_gap_that_reaches_the_talker_is_a_correction(
    settings: VoiceSettings, yes_rule: FakeYesRule, moves: Moves
) -> None:
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await io.turn_opened(1)  # in the gap: nothing of the read-back has played yet
        await clause(io, 0)
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, CALLER_WORDS, language="en")
        await settle()

    asyncio.run(drive())
    assert moves == [("confirming", "correction")]
    assert session._confirming.state == "declined"


@pytest.mark.parametrize("end", ["stop", "ending"])
def test_the_clients_stop_or_the_calls_end_moves_nothing(
    settings: VoiceSettings, moves: Moves, end: str
) -> None:
    """The table has no event for them: confirming ends, and the action stays as it was."""
    io, session, _ = confirm_call(settings, FakeJobs())

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        if end == "stop":
            await io.client({"v": 1, "type": "stop"})
        else:
            await io.ending()

    asyncio.run(drive())
    assert moves == [] and not session._confirming.active
    assert session._confirming.state == "confirming"


def test_a_move_the_table_refuses_is_logged_by_its_names_and_the_call_goes_on(
    settings: VoiceSettings,
    yes_rule: FakeYesRule,
    flow_refusals: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    monkeypatch.setattr(read_back_flow, "moved", lambda state, event: None)
    jobs = FakeJobs()
    io, session, _ = confirm_call(settings, jobs)

    async def drive(io: FakeSessionIO) -> None:
        await read_back_played(io)
        await talked(io, 1, YES)

    asyncio.run(drive(io))
    assert len(jobs.runs) == 1 and not session._confirming.active  # the yes went through
    assert session._confirming.state == "confirming"  # the state kept
    [record] = [r for r in caplog.records if r.getMessage() == REFUSED]
    assert record.levelno == logging.ERROR
    fields: dict[str, Any] = dict(record.fields)  # type: ignore[attr-defined]
    assert fields == {
        "call_id": io.setup.call_id,
        "action": ACTION,
        "state": "confirming",
        "flow_event": "yes",
    }
    logged = shown(caplog=caplog)
    for value in (DRAFT, SUMMARY, YES):  # GP-19
        assert holding(value, logged) == []
