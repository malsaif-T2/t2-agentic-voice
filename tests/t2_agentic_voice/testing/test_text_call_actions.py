"""`TextCall` with an action (testing/text_call.py; plan 007, Track D), on the real session: a turn
said over a read-back's summary or its closing question, as each plays; a fault armed for the
next summary; the caller's words typed, as the yes rule reads them; the part that acts put on
the call's setup, over its outbox; and what a turn did with an action, as its expectations read
it. Tracks B and C fill the talker's read-back and the session's confirming, so the talker here
is the tests' scripted one, keeping each plan from the session and saying its lines as clauses,
and the part that acts is a fake (action_support.py)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.testing.text_read_back import readings, summary_played_at
from t2_agentic_voice.testing.text_watch import RecordingJobs, plans_of
from t2_agentic_voice.voice.session.session_events import SessionEvent, Transcribed

from tests.t2_agentic_voice.testing.action_support import (
    CLAIM,
    FakeJobs,
    agent_with,
    completed,
    confirmed,
    plan_of,
    read_back_steps,
    stand_in_claims,
    stand_in_record,
)
from tests.t2_agentic_voice.testing.text_call_support import (
    AGENT,
    Ran,
    ScriptedCall,
    Step,
    answer,
)

PLAN = plan_of()
REQUEST = "book room R-204, the projector is broken"
OUTCOME = "Done, number 5101."


def _booking(turn: TalkerTurn) -> list[Step]:
    """The read-back first; the ask-again over a bare yes; the sending line and the outcome
    after a yes, as Track C's session will say them."""
    if turn.turn_id == 0:
        return list(read_back_steps(PLAN))
    if turn.words == "yes":
        return answer(PLAN.asked_again.text)
    return answer(PLAN.sending.text, OUTCOME)


def _started(call: ScriptedCall, turn_id: int) -> float:
    """When the caller began saying turn `turn_id`, on the call's clock."""
    return call._said[turn_id].spoke_at


def test_a_turn_said_during_the_read_back_begins_over_its_summary() -> None:
    async def scene() -> tuple[float, float, float]:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            await call.user(REQUEST)
            await call.user("yes", during="read_back")
            await call.advance(10.0)
            summary = call._parts()[1].playback.reply(1)
            assert summary is not None
            queued, played = summary.clauses[0].queued_at, summary.clauses[0].played_at
            assert queued is not None and played is not None
            return queued, _started(call, 1), played

    queued, began, played = asyncio.run(scene())
    assert queued <= began < played


def test_a_turn_said_during_the_closing_question_begins_over_it() -> None:
    async def scene() -> tuple[float, float, float]:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            await call.user(REQUEST)
            await call.user("yes", during="closing_question")
            reply = call._parts()[1].playback.reply(1)
            assert reply is not None
            summary_end, question = reply.clauses[0].played_at, reply.clauses[1]
            assert summary_end is not None and question.queued_at is not None
            assert question.queued_at >= summary_end
            await call.advance(10.0)
            assert question.played_at is not None
            return question.queued_at, _started(call, 1), question.played_at

    queued, began, played = asyncio.run(scene())
    assert queued <= began < played


def test_a_turn_said_during_a_read_back_that_never_plays_fails_saying_so() -> None:
    async def scene() -> None:
        async with ScriptedCall(lambda turn: answer("Hello there."), agent=AGENT) as call:
            await call.user(REQUEST)
            with pytest.raises(AssertionError, match="no read-back's summary played"):
                await call.user("yes", during="read_back")

    asyncio.run(scene())


def test_the_callers_words_are_typed_as_the_yes_rule_reads_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handed: list[SessionEvent] = []

    async def scene() -> None:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            side = call._parts()[0]
            hand = side.hand

            def spy(event: SessionEvent) -> None:
                handed.append(event)
                hand(event)

            monkeypatch.setattr(side, "hand", spy)
            await call.user(REQUEST)
            await call.user("yes", during="read_back")  # an overlap: its parts typed too

    asyncio.run(scene())
    sources = [e.source for e in handed if isinstance(e, Transcribed)]
    assert len(sources) >= 2 and set(sources) == {"typed"}


@pytest.mark.parametrize("fault", ["cut_short", "no_audio", "failed"])
def test_a_fault_armed_for_the_read_back_spoils_its_summary_once(fault: Any) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [SpokenClause(text="Sure.", language="en"), *read_back_steps(PLAN)]

    async def scene() -> list[float | None]:
        async with ScriptedCall(script, agent=agent_with()) as call:
            call.fault_read_back(fault)
            await call.user(REQUEST)
            await call.advance(15.0)
            await call.user("and the screen too")
            await call.advance(15.0)
            playback = call._parts()[1].playback
            first, second = readings(playback, plans_of(call._watched))
            spoiled = playback.reply(first.reply_id)
            assert spoiled is not None and spoiled.clauses[0].played  # "Sure." plays whole
            return [summary_played_at(playback, first), summary_played_at(playback, second)]

    first, second = asyncio.run(scene())
    assert first is None and second is not None


def test_the_part_that_acts_is_put_on_the_calls_setup_over_its_outbox() -> None:
    given = MemoryOutbox()

    async def scene() -> None:
        async with ScriptedCall(_booking, agent=agent_with(), outbox=given) as call:
            jobs = call._parts()[1].setup.action_jobs
            assert isinstance(jobs, RecordingJobs) and isinstance(jobs.inner, ActionRunner)
            assert jobs.inner._outbox is given and jobs.inner._record is call._record
            assert call.outbox is given
        async with ScriptedCall(_booking, agent=AGENT) as call:
            assert call._parts()[1].setup.action_jobs is None and call._jobs is None
            assert isinstance(call.outbox, MemoryOutbox)

    asyncio.run(scene())


async def _confirm(call: ScriptedCall, turn_id: int, *, speech_at: float) -> FakeJobs:
    """The session's hand-off of the yes of turn `turn_id` to the part that acts, as Track C's
    will make it, to a fake of Track B's runner."""
    jobs = call._jobs
    assert jobs is not None
    fake = FakeJobs()
    jobs.inner = fake
    clock = call._time
    await jobs.run(
        confirmed(PLAN, turn_id=turn_id, speech_at=speech_at),
        caller=Caller(subject="text-call"),
        call_id="text-call",
        language="en",
        turn_id=turn_id,
        conversation=(),
        clock=clock,
    )
    return fake


def test_a_turns_action_expectations_read_what_was_said_and_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stand_in_claims(monkeypatch)
    stand_in_record(monkeypatch)

    async def scene() -> tuple[Any, ...]:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            asked = await call.user(REQUEST)
            bare = await call.user("yes")  # the talker stands in for the session's ask-again
            await call.advance(10.0)
            yes = await call.user("yes send it")
            fake = await _confirm(call, 2, speech_at=_started(call, 2))
            await call.advance(10.0)
            return asked, bare, yes, fake, call.violations

    asked, bare, yes, fake, violations = asyncio.run(scene())
    asked.expect.read_back(contains="R-204", room="R-204")
    asked.expect.read_back()
    bare.expect.no_read_back()
    bare.expect.asked_again()
    bare.expect.no_action()
    yes.expect.confirmed("book_visit", room="R-204", note="the projector is broken")
    yes.expect.action_completed("book_visit")
    assert [c.turn_id for c in fake.ran] == [2] and violations == ()
    with pytest.raises(AssertionError, match=r"\['note'\]") as raised:
        asked.expect.read_back(note="a made-up note")
    assert "made-up" not in str(raised.value) and "projector" not in str(raised.value)
    with pytest.raises(AssertionError, match="read back"):
        asked.expect.no_read_back()
    with pytest.raises(AssertionError, match="not asked again"):
        asked.expect.asked_again()
    with pytest.raises(AssertionError, match="confirmed"):
        yes.expect.no_action()
    with pytest.raises(AssertionError, match="confirmed no book_visit"):
        bare.expect.confirmed("book_visit")
    with pytest.raises(AssertionError, match="ended done, not failed"):
        yes.expect.action_ended("book_visit", "failed")
    with pytest.raises(AssertionError, match="read no draft back"):
        bare.expect.read_back()


def test_an_outcome_said_with_no_sending_line_before_it_fails_its_expectation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stand_in_claims(monkeypatch)

    def script(turn: TalkerTurn) -> list[Step]:
        return list(read_back_steps(PLAN)) if turn.turn_id == 0 else answer(OUTCOME)

    async def scene() -> Any:
        async with ScriptedCall(script, agent=agent_with()) as call:
            await call.user(REQUEST)
            yes = await call.user("yes send it")
            await _confirm(call, 1, speech_at=_started(call, 1))
            await call.advance(10.0)
            return yes

    yes = asyncio.run(scene())
    with pytest.raises(AssertionError, match="never said to be sending"):
        yes.expect.action_completed("book_visit")


def test_the_talkers_words_after_its_action_call_are_a_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stand_in_claims(monkeypatch)

    def script(turn: TalkerTurn) -> list[Step]:
        steps = read_back_steps(PLAN)[:-1]
        return [*steps, SpokenClause(text="Anything else?", language="en"), ReplyDone()]

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script, agent=agent_with()) as call:
            await call.user(REQUEST)
            await call.advance(10.0)
            return call.violations

    (found,) = asyncio.run(scene())
    assert "spoke after its action call" in found and "Anything else?" in found


def _status(number: str) -> tuple[Tool, Ran]:
    """A tool that reports on the action, and its call, returned `number`."""

    async def status() -> ToolResult:
        return ToolResult(data={"number": number}, evidence=(number,))

    tool = Tool.from_function(
        status, name="visit_status", description="A visit's status.", reports_on=["book_visit"]
    )
    request = ToolCallRequest(id="t-9", name="visit_status", arguments="{}")
    return tool, Ran(request, ToolResult(data={"number": number}, evidence=(number,)))


def test_a_claim_is_a_violation_unless_a_record_or_a_status_backs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule A is Track A's, stood in for: it is asked of every clause the talker said, with the
    action's own phrases, the defaults, and what backs each action."""
    claimed = stand_in_claims(monkeypatch)
    tool, ran = _status("5101")

    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:  # a number the caller said backs no claim
            return answer(f"Your {CLAIM}, number 7303.")
        return [ran, *answer(f"Your {CLAIM}, number 5101.")]

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script, agent=agent_with(tools=[tool])) as call:
            for words in ("is 7303 booked", "and now"):
                await call.user(words)
                await call.advance(10.0)
            return call.violations

    (found,) = asyncio.run(scene())
    assert found.startswith("turn 0 claimed book_visit with no record") and "7303" in found
    asked = {call["clause"]: call for call in claimed.calls}
    backing = asked[f"Your {CLAIM}, number 5101."]
    assert backing["claims"] == {"book_visit": (CLAIM,)}
    assert backing["any_action"] == ("i've booked",)
    assert [(e.action, "5101" in e.texts) for e in backing["evidence"]] == [("book_visit", True)]


def test_the_records_entries_back_a_claim_once_a_job_ran(monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in_claims(monkeypatch)
    stand_in_record(monkeypatch, (completed(number="5101"),))

    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:
            return list(read_back_steps(PLAN))
        return answer(PLAN.sending.text, OUTCOME, f"Your {CLAIM}, number 5101.")

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script, agent=agent_with()) as call:
            await call.user(REQUEST)
            await call.user("yes send it")
            await _confirm(call, 1, speech_at=_started(call, 1))
            await call.advance(10.0)
            return call.violations

    assert asyncio.run(scene()) == ()


def test_a_yes_before_its_summary_played_whole_or_unsealed_is_a_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stand_in_claims(monkeypatch)
    stand_in_record(monkeypatch)

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            call.fault_read_back("cut_short")
            await call.user(REQUEST)
            yes = await call.user("yes send it")
            await _confirm(call, yes.turn_id, speech_at=_started(call, yes.turn_id))
            jobs = call._jobs
            assert jobs is not None
            early = confirmed(PLAN, turn_id=1, speech_at=0.5)
            # One the yes rule never issued: a copy of a sealed one cannot even be made.
            forged = SimpleNamespace(**{**early.model_dump(), "speech_at": 99.0})
            for each in (early, forged):
                await jobs.run(each, **jobs.runs[0].given)  # type: ignore[arg-type]
            await call.advance(10.0)
            return call.violations

    found = asyncio.run(scene())
    assert len(found) == 3
    assert sum("began before a read-back of its draft played whole" in f for f in found) == 2
    assert sum("ran with no yes the yes rule issued" in f for f in found) == 1
    assert all("yes send it" not in f for f in found)  # never the caller's words


def test_a_job_handed_on_again_is_kept_as_a_second_run(monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in_record(monkeypatch)

    async def scene() -> list[int]:
        async with ScriptedCall(_booking, agent=agent_with()) as call:
            await call.user(REQUEST)
            yes = await call.user("yes send it")
            fake = await _confirm(call, yes.turn_id, speech_at=_started(call, yes.turn_id))
            jobs = call._jobs
            assert jobs is not None
            again = await jobs.again(jobs.runs[0])
            assert again.kind == "done" and jobs.runs[1].given == jobs.runs[0].given
            assert jobs.runs[1].confirmed is jobs.runs[0].confirmed
            return [c.turn_id for c in fake.ran]

    assert asyncio.run(scene()) == [1, 1]
