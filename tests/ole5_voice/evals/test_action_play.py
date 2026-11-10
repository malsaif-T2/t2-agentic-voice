"""One play of run A end to end (action_play.py, action_call.py, action_backend.py): Ole5's agent
on its mock ticket system, the library's `TextCall` with its talker on a `FunctionLLM` that calls
the actions as tools (action_run_support.py's oracle), the session's own read-back and
confirming, the real yes rule, guard and action runner over an outbox in memory; nothing
monkeypatched, nothing sent. Each committed scenario passes when the agent does what it
expects; the mock, seeded as the scenario says, keeps what the call made; and what the run must
see is seen: a claim the guard blocks, a write with no scripted yes (in a play with no result
too), a passage first in the search, a judge's failing check, a provider's failure."""

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
from ole5_voice.evals.action_score import ActionPlayRecord
from ole5_voice.evals.action_setup import AgentFactory
from ole5_voice.evals.chat_pacing import Limits, ModelPacer, PacedChat, Price, Spend
from ole5_voice.evals.judge import Judge
from ole5_voice.evals.kb_points import RecordingKnowledge
from ole5_voice.tickets.mock import FILE_NAME
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.evals import FakeKnowledgeBase

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
            settings=VoiceSettings.model_validate({"env": "test", "llm": llm}),
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
