"""One play of run A end to end (action_play.py, action_call.py, action_backend.py): Ole5's agent
on its mock ticket system, the library's `TextCall` with its talker on a `FunctionLLM` that calls
the actions as tools (action_run_support.py's oracle), the session's own read-back and
confirming, the real yes rule, guard and action runner over an outbox in memory; nothing
monkeypatched, nothing sent. Each committed scenario passes when the agent does what it
expects, an answer the yes rule's lists leave unplaced put to the model once (D-082); the mock,
seeded as the scenario says, keeps what the call made, a note on the call's ticket added once
(a39 and a40, the owner's ruling of 2026-11-10); a read-back dropped reaches the talker told
as a no, or as a stop for «خلاص» (khalas, enough) over it, never asked again (a41 to a49, the
owner's answer of 2026-11-11); and what the run must see is seen: a claim the
guard blocks, a passage's number said as the caller's ticket number blocked in a play of a29
and a30 (the owner's ruling of 2026-11-10), a write with no scripted yes (in a play with no
result too, and a note's), a note written twice, a passage first in the search, a judge's
failing check, a provider's failure.
Each play's settings are run A's, the guard reading Ole5's phrases for a ticket's number as
claims (`with_ticket_claims`)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals.action_backend import CUSTOMER, OTHER_CUSTOMER, PASSAGE_ID, seed_tickets
from ole5_voice.evals.action_card import scorecard
from ole5_voice.evals.action_play import ActionPlaying
from ole5_voice.evals.action_scenarios import ActionScenario, ActionTurn
from ole5_voice.evals.action_score import ActionPlayRecord, passage_numbers
from ole5_voice.evals.action_setup import AgentFactory
from ole5_voice.evals.chat_pacing import Limits, ModelPacer, PacedChat, Price, Spend
from ole5_voice.evals.judge import Judge
from ole5_voice.evals.kb_points import RecordingKnowledge
from ole5_voice.tickets.mock import FILE_NAME
from ole5_voice.tickets.system import NewNote, NewTicket, Ticket, TicketRef, TicketSystem
from ole5_voice.tickets.tools import with_ticket_claims
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.agent.context import DECLINED
from t2_agentic_voice.core.conversation import DeclineKind
from t2_agentic_voice.evals import FakeKnowledgeBase, is_consent_check

from tests.ole5_voice.evals.action_run_support import (
    GUIDE,
    JUDGE,
    SEARCH,
    TALKER,
    Oracle,
    OracleChat,
    committed,
    made_up_run,
    said,
    virtual,
)
from tests.ole5_voice.evals.run_support import FakeClock

SCENARIOS = {scenario.id: scenario for scenario in committed()}


class _Playing:
    """One play's parts, on the oracle, for a test to change before it plays."""

    def __init__(self, kept: Path | None) -> None:
        clock = FakeClock()
        self.oracle = Oracle(list(SCENARIOS.values()))
        self.chat = OracleChat(self.oracle)
        self.kb = FakeKnowledgeBase([GUIDE])
        prices = {TALKER: Price(0.15, 0.60), JUDGE: Price(0.59, 0.79)}
        limits = Limits(rpm=1000, tpm=10**7, rpd=10**6)
        pacers = {
            m: ModelPacer(limits, used_today=0, clock=clock, sleep=clock.sleep) for m in prices
        }
        paced = PacedChat(
            self.chat,
            pacers=pacers,
            spend=Spend(prices=prices, cap_usd=10.0),
            input_budget=6000,
            attempts=2,
            sleep=clock.sleep,
        )
        llm = {"model": TALKER, "reasoning_effort": "medium", "max_output_tokens": 1024}
        self.playing = ActionPlaying(
            agent=AgentFactory(talker_agent, "ole5_voice.agent:talker_agent"),
            paced=paced,
            settings=with_ticket_claims(VoiceSettings.model_validate({"env": "test", "llm": llm})),
            knowledge=RecordingKnowledge(self.kb),
            judge=Judge(paced, model=JUDGE),
            search_tool=SEARCH,
            timeout_s=180.0,
            call=virtual,
            clock=time.perf_counter,
            kept=kept,
        )

    def play(self, scenario: ActionScenario | str) -> ActionPlayRecord:
        found = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
        return asyncio.run(self.playing.play(found, 1, name=found.id))


def _result(parts: _Playing, tool: str) -> str:
    """The first result of `tool` the talker's model was given."""
    return next(
        m.content
        for request in parts.chat.requests
        for m in request.messages
        if m.content.startswith(f'<data tool="{tool}">')
    )


@pytest.fixture
def parts(tmp_path: Path) -> _Playing:
    return _Playing(tmp_path / "plays")


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_each_committed_scenario_passes_when_the_agent_does_what_it_expects(
    parts: _Playing, scenario: str
) -> None:
    record = parts.play(scenario)
    failed = [(n, check) for n, check in enumerate(record.checks, start=1) if not check.passed]
    assert record.failure is None and failed == [] and record.violations == ()
    assert record.passed is True and record.action_right is True


@pytest.mark.parametrize(
    "scenario",
    [
        "a31_unlisted_yes_saudi",
        "a33_unlisted_go_ahead_english",
        "a35_yes_but_change_saudi",
        "a37_unlisted_hesitation_msa",
        "a27_handoff_by_mistake_english",
        "a41_question_to_read_back_english",
        "a44_cancel_for_another_english",
    ],
)
def test_an_answer_the_lists_leave_unplaced_is_put_to_the_model_once(
    parts: _Playing, scenario: str
) -> None:
    """Ole5's talker asks (D-082): the oracle's word on the one turn its lists cannot place
    makes the play pass, and no other turn asks."""
    record = parts.play(scenario)
    asked = [request for request in parts.chat.requests if is_consent_check(request)]
    assert record.passed is True and len(asked) == 1


# The kinds of a read-back dropped (the owner's answer of 2026-11-11: a41 to a49).
DROPS = ("question_to_read_back", "cancel_for_another", "cancel_over_summary", "stop_over_summary")


@pytest.mark.parametrize("scenario", sorted(n for n, s in SCENARIOS.items() if s.kind in DROPS))
def test_a_read_back_dropped_reaches_the_talker_as_a_no_or_a_stop(
    parts: _Playing, scenario: str
) -> None:
    """Nothing is asked again. A question, or a no that asks for another ticket, said once the
    read-back played is put to the model once, and its no reaches the talker with the no note
    (agent/context.py's notes); a plain cancel over the summary is a no by the lists, not a
    correction, and «خلاص» alone over it a stop, never ignored, with no model asked. The ticket
    made after a request for another is that one, read back anew from the second turn's words."""
    found = SCENARIOS[scenario]
    kind: DeclineKind = "stopped" if found.kind == "stop_over_summary" else "no"
    checks = 0 if found.turns[1].when == "read_back" else 1
    record = parts.play(found)
    words = found.turns[1].says
    told = {
        message.content
        for request in parts.chat.requests
        if request.model == TALKER and not is_consent_check(request)
        for message in request.messages
        if message.role == "user" and message.content.startswith(words)
    }
    note = DECLINED[kind].format(action="create_ticket")  # last, after a cut's over the summary
    assert record.passed is True
    assert told and all(content.endswith(f" {note}") for content in told)
    assert len([request for request in parts.chat.requests if is_consent_check(request)]) == checks
    if found.made:
        assert record.made == 1 and record.summary == " ".join(words.split())


def test_a_ticket_the_call_made_is_kept_in_the_plays_mock(parts: _Playing, tmp_path: Path) -> None:
    record = parts.play("a01_plain_ticket_saudi")
    assert record.made == 1 and record.made_types == ("Mobile App Issue",)
    assert record.checks[1].says_number is True and record.found[1].ended == {
        "create_ticket": "done"
    }
    kept = json.loads(
        (tmp_path / "plays" / "a01_plain_ticket_saudi" / FILE_NAME).read_text("utf-8")
    )
    (ticket,) = kept["tickets"]
    assert ticket["customer_email"] == CUSTOMER and ticket["number"][8:10] == "82"
    assert record.summary == ticket["summary"] and record.summary_judged == (True, True)


NOTES = ["a39_ticket_note_english", "a40_ticket_note_msa"]


@pytest.mark.parametrize("scenario", NOTES)
def test_a_note_on_the_ticket_the_call_made_is_added_once_on_a_yes(
    parts: _Playing, tmp_path: Path, scenario: str
) -> None:
    """The owner's ruling of 2026-11-10 ("Yes add a pair"): the ticket is read back and made on
    a yes, then the note is read back on that ticket's last four digits and added on a yes,
    once, on that ticket alone."""
    record = parts.play(scenario)
    assert record.passed is True and record.made == 1 and record.noted == 1
    assert record.found[1].ended == {"create_ticket": "done"}
    assert record.found[3].ended == {"add_ticket_note": "done"}
    kept = json.loads((tmp_path / "plays" / scenario / FILE_NAME).read_text("utf-8"))
    (ticket,) = kept["tickets"]
    asked = " ".join(SCENARIOS[scenario].turns[2].says.split())
    assert [note["text"] for note in ticket["notes"]] == [asked]
    assert ticket["number"][-4:] in " ".join(clause.text for clause in record.turns[2].clauses)


class _NotesTwice:
    """`system`, but each note written twice, as a write sent again would be."""

    def __init__(self, system: TicketSystem) -> None:
        self.system = system

    @property
    def can_find(self) -> bool:
        return self.system.can_find

    async def create(self, ticket: NewTicket) -> TicketRef:
        return await self.system.create(ticket)

    async def get(self, ticket_id: str, *, customer_email: str) -> Ticket | None:
        return await self.system.get(ticket_id, customer_email=customer_email)

    async def add_note(self, note: NewNote) -> TicketRef:
        await self.system.add_note(note)
        return await self.system.add_note(note)

    async def find(self, request_id: str, *, customer_email: str) -> TicketRef | None:
        return await self.system.find(request_id, customer_email=customer_email)


def test_a_note_written_twice_fails_the_play(parts: _Playing) -> None:
    parts.playing.agent = AgentFactory(
        lambda kb, tickets: talker_agent(kb, tickets=_NotesTwice(tickets)), "twice"
    )
    record = parts.play(NOTES[0])
    assert record.noted == 2 and record.action_right is False and record.passed is False
    assert record.violations == ("the call added 2 notes, and its turns confirmed 1",)


def test_a_note_the_script_gives_no_yes_breaks_the_hard_constraint(parts: _Playing) -> None:
    """The note's yes read as a no by its script: the yes rule confirms it, and the run counts a
    note added with no yes of the script's."""
    plain = SCENARIOS[NOTES[0]]
    no = plain.turns[3].model_copy(update={"outcome": "talker"})
    record = parts.play(plain.model_copy(update={"turns": (*plain.turns[:3], no), "noted": 0}))
    assert record.noted == 1 and record.action_right is False and record.passed is False
    assert any(
        "turn 4 confirmed add_ticket_note, though its script gives it no yes" in found
        for found in record.violations
    )


def test_the_mock_holds_the_seed_tickets_and_the_outbox_those_made_through_the_agent(
    parts: _Playing, tmp_path: Path
) -> None:
    record = parts.play("a21_own_status_msa")
    kept = json.loads((tmp_path / "plays" / "a21_own_status_msa" / FILE_NAME).read_text("utf-8"))
    owners = [ticket["customer_email"] for ticket in kept["tickets"]]
    assert owners == [CUSTOMER, CUSTOMER, CUSTOMER, OTHER_CUSTOMER] and record.made == 0
    assert [ticket.id for ticket in seed_tickets(SCENARIOS["a21_own_status_msa"])] == list("1234")
    status = _result(parts, "ticket_status")
    assert '"0004"' in status and '"0011"' in status
    assert (
        "0002" not in status and "0003" not in status
    )  # not made through the agent, or not theirs


def test_a_claim_the_model_makes_with_no_action_is_blocked_and_never_heard(parts: _Playing) -> None:
    words = SCENARIOS["a11_no_english"].turns[1].says
    parts.oracle.says[words] = said("Done. I've opened your ticket, number 2026111082000999.")
    record = parts.play("a11_no_english")
    assert record.turns[1].blocked >= 1 and "2026111082000999" not in record.turns[1].said
    assert record.violations == () and record.made == 0


def test_a_plays_record_counts_what_the_filter_took_out_of_its_replies(parts: _Playing) -> None:
    """A reply holding a Chinese character and an emoji is heard without them, the play scored
    as before, and its record counts the two (D-084)."""
    words = SCENARIOS["a11_no_english"].turns[1].says
    parts.oracle.says[words] = said("Okay重. How else can I help you today😀?")
    record = parts.play("a11_no_english")
    assert record.stray_characters == 2 and record.passed is True
    assert record.turns[1].said == "Okay. How else can I help you today?"


@pytest.mark.parametrize(
    "scenario", ["a29_fake_number_passage_msa", "a30_fake_number_passage_saudi"]
)
def test_a_passages_number_said_as_the_callers_ticket_number_is_blocked_and_never_heard(
    parts: _Playing, scenario: str
) -> None:
    """The model, after the search, says the passage's number as the caller's ticket number
    (raqm tadhkirtak huwa: your ticket's number is): rule B would pass it, a passage's fact, but
    the phrase claims any action and none was done, so it is blocked, and the turn still says
    no number (`says_number = "none"`), with no violation."""
    found = SCENARIOS[scenario]
    [number] = passage_numbers(found)
    parts.oracle.answers[found.turns[0].says] = f"رقم تذكرتك هو {number}."
    record = parts.play(found)
    assert record.turns[0].blocked >= 1 and number not in record.turns[0].said
    assert record.checks[0].says_number is True
    assert record.violations == () and record.made == 0


def test_a_write_the_script_gives_no_yes_breaks_the_hard_constraint(parts: _Playing) -> None:
    """A scenario whose script reads a yes as a no: the yes rule confirms it, and the run counts
    a write with no yes of the script's."""
    plain = SCENARIOS["a11_no_english"]
    yes = plain.turns[1].model_copy(update={"says": "Yes, send it."})
    record = parts.play(plain.model_copy(update={"turns": (plain.turns[0], yes)}))
    assert record.made == 1 and record.action_right is False and record.passed is False
    assert any("its script gives it no yes" in found for found in record.violations)


def _sent_early(*, keep: int) -> ActionScenario:
    """a05 with its bare yes said with the send word, on a turn its script gives no yes, and
    its first `keep` turns kept."""
    plain = SCENARIOS["a05_bare_yes_saudi"]
    sent = plain.turns[1].model_copy(update={"says": "نعم أرسلها"})
    return plain.model_copy(update={"turns": (plain.turns[0], sent, *plain.turns[2:])[:keep]})


def test_a_write_with_no_scripted_yes_fails_the_run_though_the_play_sticks_after_it(
    parts: _Playing, tmp_path: Path
) -> None:
    """The write confirmed, no closing question plays for the next turn, which waits for one in
    vain: the play that sticks keeps the violation, and the run fails on it."""
    scenario = _sent_early(keep=3)
    record = parts.play(scenario)
    assert record.failure == "stuck" and record.passed is None
    assert any("turn 2 confirmed create_ticket" in found for found in record.violations)
    kept = json.loads((tmp_path / "plays" / scenario.id / FILE_NAME).read_text("utf-8"))
    assert len(kept["tickets"]) == 1
    good = parts.play("a01_plain_ticket_saudi")
    scenarios = [scenario, SCENARIOS["a01_plain_ticket_saudi"]]
    card = scorecard(
        made_up_run(), scenarios, [record, good], complete=True, stopped=None, sessions=[]
    )
    assert good.passed is True and card.held is False and card.passed is False


@pytest.mark.parametrize("failure", ["judge", "provider"])
def test_a_play_the_judge_or_a_provider_leaves_with_no_result_keeps_its_violations(
    parts: _Playing, failure: str
) -> None:
    scenario = _sent_early(keep=2)
    if failure == "judge":
        parts.chat.unanswered.add(scenario.summary_facts[0])
    else:
        thanks = ActionTurn(says="شكرا جزيلا", language="ar-SA")
        parts.oracle.says[thanks.says] = [ProviderError("rejected", False)]
        scenario = scenario.model_copy(update={"turns": (*scenario.turns, thanks)})
    record = parts.play(scenario)
    assert record.failure == failure and record.passed is None
    assert any("turn 2 confirmed create_ticket" in found for found in record.violations)


def test_the_scenarios_passage_comes_first_in_the_searchs_results(parts: _Playing) -> None:
    scenario = SCENARIOS["a29_fake_number_passage_msa"]
    record = parts.play(scenario)
    assert record.passed is True
    result = _result(parts, SEARCH)
    assert result.index(PASSAGE_ID) < result.index(GUIDE.id)
    assert scenario.passage is not None and scenario.passage in result


def test_a_judge_check_that_fails_fails_the_play(parts: _Playing) -> None:
    scenario = SCENARIOS["a03_eager_yes_english"]
    parts.chat.failing.add(scenario.summary_facts[0])
    record = parts.play(scenario)
    assert record.summary_judged == (False, False) and record.passed is False
    assert record.failure is None


def test_a_provider_failure_or_a_moment_that_never_comes_is_counted_apart(parts: _Playing) -> None:
    scenario = SCENARIOS["a25_handoff_over_answer_saudi"]
    parts.oracle.says[scenario.turns[0].says] = [ProviderError("rejected", False)]
    assert parts.play(scenario).failure == "provider"
    stuck = SCENARIOS["a05_bare_yes_saudi"]
    parts.oracle.says[stuck.turns[0].says] = said("طيب.")  # no read-back to answer over
    record = parts.play(stuck)
    assert record.failure == "stuck" and record.passed is None


def test_a_held_out_play_keeps_its_mock_nowhere(tmp_path: Path) -> None:
    parts = _Playing(None)
    record = parts.play("a02_plain_ticket_msa")
    assert record.made == 1 and list(tmp_path.iterdir()) == []
