"""An action's read-back in the session, and its receipt (voice/session/read_back.py; plan 007,
Track C; docs/SECURITY.md, invariant 1): the talker's `ReadBackRequested` plays the summary, then
the closing question, as the reply's next clauses, each said in its spoken form, captioned in its
text and marked with its part, and the client is shown `confirming` whenever no reply plays; it
plays when the talker's event plays, so an early start let go before then confirms nothing. The
receipt is built only when asked for (when the yes rule is called): never before the summary's
last clause played whole with audio, never for speech begun before that, never while an overlap
of the summary is undecided, and its `question_ended_at` only from the question's last
`ClausePlayed`. A call that reads nothing back is shown no `confirming`."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import ConfirmationRequested
from t2_agentic_voice.core.yes_inputs import ReadBackReceipt, is_read_back_receipt
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.voice.protocol import Caption, Notice
from t2_agentic_voice.voice.session import read_back
from t2_agentic_voice.voice.session.session_events import ClausePlayed, SessionEvent

from tests.t2_agentic_voice.voice.session.overlap_support import LISTENING, FakeRule, two_step
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    DRAFT,
    PLAN,
    QUESTION,
    REQUEST,
    SUMMARY,
    SUMMARY_SPOKEN,
    asked,
    clause,
    read_whole,
    reads_back,
    receipt,
    states,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    emitted,
    greeted,
    play,
    sent,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    Step,
    settle,
    talked,
    talker_call,
)


def _played_at(events: list[SessionEvent], index: int) -> float:
    """When reply 1's clause `index` reported it played."""
    found = [e for e in events if isinstance(e, ClausePlayed) and e.reply_id == 1]
    (played,) = [e for e in found if e.clause == index]
    return played.at


def test_a_read_back_says_its_summary_then_its_question_and_the_call_is_confirming(
    settings: VoiceSettings,
) -> None:
    io, session, _ = talker_call(two_step(settings), reads_back)

    async def drive() -> None:
        await asked(io)
        assert session._confirming.active
        assert states(io)[-1] == "confirming"  # asked for, no audio yet
        assert emitted(io, ConfirmationRequested) == []
        await clause(io, 0, played=False)
        assert states(io)[-1] == "speaking"
        (began,) = emitted(io, ConfirmationRequested)  # its first audio
        assert (began.turn_id, began.action) == (0, ACTION)
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert len(emitted(io, ConfirmationRequested)) == 1  # once, not again for the question
    assert [s.text for s in speaks(io, 1)] == [provider_text(SUMMARY_SPOKEN), QUESTION]
    reply = session.playback.reply(1)
    assert reply is not None and reply.ended_at is not None
    assert [(c.caption, c.part) for c in reply.clauses] == [
        (SUMMARY, "summary"),
        (QUESTION, "question"),
    ]
    agent = [c.text for c in sent(io, Caption) if c.speaker == "agent"]
    assert agent[-2:] == [SUMMARY, QUESTION]  # captioned as written, the number as issued
    assert states(io)[-1] == "confirming"  # the read-back has played: waiting for the answer
    assert session._confirming.active
    assert sent(io, Notice) == []  # a reply that only read back is no empty answer


def test_a_summary_longer_than_one_request_is_several_clauses_each_marked(
    settings: VoiceSettings,
) -> None:
    long_summary = "Made-up first part of the summary, " + "made-up words " * 12 + "end."
    summary = PLAN.summary.model_copy(update={"text": long_summary, "spoken": long_summary})
    plan = PLAN.model_copy(update={"summary": summary})

    def script(turn: TalkerTurn) -> list[Step]:
        return [ReadBackRequested(plan=plan), *reads_back(turn)[1:]]

    io, session, _ = talker_call(two_step(settings), script, max_chars=60)
    asyncio.run(asked(io))
    current = session._confirming.read_back
    assert current is not None and len(current.summary) > 1
    reply = session.playback.reply(1)
    assert reply is not None
    parts = [c.part for c in reply.clauses]
    assert parts == ["summary"] * len(current.summary) + ["question"] * len(current.question)
    assert current.question == tuple(range(len(current.summary), len(parts)))


def test_the_receipt_is_built_only_when_asked_and_holds_the_draft_read_back(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[dict[str, Any]] = []
    real = read_back.played_receipt

    def counted(**values: Any) -> ReadBackReceipt:
        built.append(values)
        return real(**values)

    monkeypatch.setattr(read_back, "played_receipt", counted)
    io, session, _ = talker_call(two_step(settings), reads_back)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)
        await settle()

    asyncio.run(drive())
    assert built == []  # nothing is built as the read-back plays
    found = receipt(session, io.clock.now() + 1.0)
    assert found is not None and is_read_back_receipt(found)
    assert (found.action, found.draft_json, found.reply_id) == (ACTION, DRAFT, 1)
    assert found.summary_played_at == _played_at(io.events, 0)
    assert found.question_ended_at == _played_at(io.events, 1)
    assert len(built) == 1


def test_no_receipt_before_the_summary_played_whole_nor_a_question_end_before_it_played(
    settings: VoiceSettings,
) -> None:
    """GP-08, invariant 1: while the summary plays there is no receipt; while the question
    plays the receipt says it has not ended; only its last `ClausePlayed` ends it."""
    io, session, _ = talker_call(two_step(settings), reads_back)
    found: dict[str, ReadBackReceipt | None] = {}

    async def drive() -> None:
        await asked(io)
        found["asked"] = receipt(session, io.clock.now())
        await clause(io, 0, played=False)
        found["summary playing"] = receipt(session, io.clock.now())
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1, played=False)
        found["question playing"] = receipt(session, io.clock.now())
        await io.clause_played(1, 1, audio_s=2.0)
        found["played"] = receipt(session, io.clock.now())

    asyncio.run(drive())
    assert found["asked"] is None and found["summary playing"] is None
    playing, played = found["question playing"], found["played"]
    assert playing is not None and playing.question_ended_at is None
    assert played is not None and played.question_ended_at == _played_at(io.events, 1)


@pytest.mark.parametrize(
    "played", [{"cut_short": True}, {"audio_s": 0.0}], ids=["cut_short", "no_audio"]
)
def test_a_summary_clause_cut_short_or_with_no_audio_earns_no_receipt(
    settings: VoiceSettings, played: dict[str, Any]
) -> None:
    io, session, _ = talker_call(two_step(settings), reads_back)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, **played)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert receipt(session, io.clock.now() + 1.0) is None
    assert not session._confirming.active  # its reply ended with no summary played whole


def test_speech_begun_before_the_summary_ended_never_earns_a_receipt(
    settings: VoiceSettings,
) -> None:
    """GP-08, invariant 1, from the session's side: the receipt is never built for a turn whose
    speech began over the summary, however the summary then played."""
    io, session, _ = talker_call(two_step(settings), reads_back)

    async def drive() -> None:
        await asked(io)
        await read_whole(io)

    asyncio.run(drive())
    summary_at = _played_at(io.events, 0)
    assert receipt(session, summary_at - 0.01) is None
    assert receipt(session, None) is None  # no turn opened for the words: before anything
    assert receipt(session, summary_at) is not None


def test_an_overlap_of_the_summary_still_undecided_denies_the_receipt(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """A verdict landing late can deny the receipt: until the overlap begun over the summary is
    decided, no receipt is built for any later turn."""
    rule.script["made-up murmur"] = LISTENING
    io, session, _ = talker_call(two_step(settings), reads_back)
    found: dict[str, ReadBackReceipt | None] = {}

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await io.turn_opened(1)  # over the summary, its whole overlap still awaited
        await io.transcribing(1, part="overlap")
        await io.clock.advance(0.2)
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1)
        found["undecided"] = receipt(session, io.clock.now())
        await io.transcribed(1, "made-up murmur", language="en", part="overlap")
        await io.turn_closed(1)
        await io.transcribed(1, "made-up murmur", language="en")
        await settle()
        found["decided"] = receipt(session, io.clock.now())

    asyncio.run(drive())
    assert found["undecided"] is None
    assert found["decided"] is not None


def test_a_read_back_held_by_an_early_start_let_go_confirms_nothing(
    settings: VoiceSettings,
) -> None:
    """The session starts confirming when the read-back plays, not when the talker writes it:
    an early start whose hold the caller resumed leaves nothing."""
    io, session, talker = talker_call(two_step(settings), reads_back)

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.clock.advance(1.0)
        await io.turn_held(0)
        await io.transcribing(0, part="held")
        await io.transcribed(0, REQUEST, language="en", part="held")
        await settle()
        assert talker.turns and not session._confirming.active  # written, kept, not played
        await io.hold_resumed(0)
        await settle()

    asyncio.run(drive())
    assert not session._confirming.active
    assert speaks(io, 1) == [] and "confirming" not in states(io)


def test_a_call_that_reads_nothing_back_is_never_shown_confirming(
    settings: VoiceSettings,
) -> None:
    io, session, _ = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, REQUEST)
        await play(io, 1)

    asyncio.run(drive())
    assert "confirming" not in states(io)
    reply = session.playback.reply(1)
    assert reply is not None and all(c.part is None for c in reply.clauses)
    assert not session._confirming.active
    assert receipt(session, io.clock.now()) is None
