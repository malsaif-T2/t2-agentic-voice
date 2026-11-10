"""Run A's checks of a play (action_score.py), its scorecard (action_card.py), its history line
(action_history.py) and its dry estimate (action_setup.py), on made-up plays: what the agent
says of a ticket number, each outcome read from what the call did, the scenario's own
violations, the registered metrics and targets, the hard constraint failing a run, a held-out
run's aggregates only, and the estimate of each committed split at the registered prices."""

from __future__ import annotations

import argparse
import dataclasses
from typing import Any

import pytest
from ole5_voice.evals.action_call import Acted, TurnFound
from ole5_voice.evals.action_card import (
    TARGETS,
    ActionScorecard,
    metrics,
    scorecard,
    targets,
)
from ole5_voice.evals.action_history import ActionLine, action_line
from ole5_voice.evals.action_run import CAP_USD
from ole5_voice.evals.action_scenarios import ActionScenario, ActionTurn
from ole5_voice.evals.action_score import (
    ActionPlayRecord,
    TurnScore,
    acting,
    number_said,
    outcome_held,
    unasked,
)
from ole5_voice.evals.action_setup import CHECK, asks, requests_of
from ole5_voice.evals.chat_pacing import Price
from ole5_voice.evals.talker_data import Clause, HeardTurn
from ole5_voice.evals.talker_score import Session
from pydantic import ValidationError

from tests.ole5_voice.evals.action_run_support import JUDGE, TALKER, committed
from tests.ole5_voice.evals.action_run_support import made_up_run as _run
from tests.ole5_voice.evals.samples import WHEN

MADE = "2026111082000917"
MINE = "2026110482000042"
OTHER = "2026110482000043"


def _said(wanted: Any, text: str, *, done: bool = False) -> bool:
    known = (MADE, MINE, OTHER)
    return number_said(text, wanted, made=(MADE,), mine=(MINE, MADE), known=known, done=done)


@pytest.mark.parametrize(
    ("wanted", "text", "done", "holds"),
    [
        ("whole", "Your ticket number is 2026, 1110, 8200, 0917.", False, True),
        ("whole", "تم، رقم تذكرتك ٢٠٢٦، ١١١٠، ٨٢٠٠، ٠٩١٧.", False, True),
        ("whole", "I'm opening the ticket now.", True, True),  # its done line said it
        ("whole", "I'm opening the ticket now.", False, False),
        ("last_four", "Your ticket ending 0042 is waiting for you.", False, True),
        ("last_four", "Your ticket 2026110482000042 is waiting.", False, False),
        ("last_four", "The ticket ending 0043 is open.", False, False),  # not the caller's
        ("none", "There is no ticket and no number.", False, True),
        ("none", "Your ticket ending 0042 is open.", False, False),
        ("none", "It takes 2 to 3 days.", False, True),
    ],
)
def test_what_the_agent_says_of_a_ticket_number(
    wanted: str, text: str, done: bool, holds: bool
) -> None:
    assert _said(wanted, text, done=done) is holds


def _turn(text: str = "", *, requests: int = 1) -> HeardTurn:
    clauses = (Clause(text=text, language="en", fate="played", played_fraction=1),) if text else ()
    return HeardTurn(fate="answered", clauses=clauses, model_requests=requests)


def _acted(*found: TurnFound, heard: tuple[HeardTurn, ...] = ()) -> Acted:
    turns = heard or tuple(_turn("Okay.") for _ in found)
    return Acted(turns=turns, found=found, violations=())


ASKED = ActionTurn(says="Open a ticket.", calls="create_ticket", outcome="read_back")


@pytest.mark.parametrize(
    ("outcome", "found", "earlier", "requests", "holds"),
    [
        ("read_back", TurnFound(read_back=True), TurnFound(), 1, True),
        (
            "read_back",
            TurnFound(read_back=True, confirmed=("create_ticket",)),
            TurnFound(),
            1,
            False,
        ),
        ("asked_again", TurnFound(asked_again=True), TurnFound(), 0, True),
        ("ignored", TurnFound(), TurnFound(read_back=True, kept=True), 0, True),
        ("ignored", TurnFound(), TurnFound(read_back=True, kept=False), 0, False),
        ("stopped", TurnFound(), TurnFound(), 1, True),
        ("declined", TurnFound(), TurnFound(), 0, True),
        ("declined", TurnFound(), TurnFound(), 1, False),
        ("talker", TurnFound(), TurnFound(), 1, True),
        ("talker", TurnFound(read_back=True), TurnFound(), 1, False),
        (
            "done",
            TurnFound(confirmed=("create_ticket",), ended={"create_ticket": "done"}),
            TurnFound(),
            0,
            True,
        ),
        (
            "done",
            TurnFound(confirmed=("create_ticket",), ended={"create_ticket": "unknown"}),
            TurnFound(),
            0,
            False,
        ),
        ("failed", TurnFound(confirmed=("create_ticket",)), TurnFound(), 0, False),  # not ended
    ],
)
def test_each_outcome_is_read_from_what_the_call_did(
    outcome: str, found: TurnFound, earlier: TurnFound, requests: int, holds: bool
) -> None:
    turns = [ASKED, ActionTurn(says="Next words.", outcome=outcome)]  # type: ignore[arg-type]
    heard = (_turn("Okay."), _turn("In my own words." if requests else "", requests=requests))
    assert outcome_held(turns, _acted(earlier, found, heard=heard), 1) is holds
    assert acting(turns, 1) == "create_ticket" and acting([ActionTurn(says="x")], 0) is None


def _scenario(**changed: Any) -> ActionScenario:
    fields: dict[str, Any] = {
        "id": "made_up",
        "kind": "plain_ticket",
        "split": "dev",
        "language": "en",
        "notes": "A made-up scenario.",
        "made": 1,
        "ticket_type": "Bug",
        "turns": [
            {
                "says": "Open a ticket, yes, send it.",
                "calls": "create_ticket",
                "outcome": "read_back",
            },
            {"says": "Yes, send it.", "outcome": "done", "says_number": "whole"},
        ],
    }
    return ActionScenario.model_validate(fields | changed)


def test_a_write_the_script_gives_no_yes_or_a_ticket_beyond_the_writes_is_a_violation() -> None:
    scenario = _scenario()
    eager = _acted(TurnFound(confirmed=("create_ticket",)), TurnFound())
    (found,) = unasked(scenario, eager, 1)
    assert "turn 1 confirmed create_ticket" in found
    right = _acted(TurnFound(), TurnFound(confirmed=("create_ticket",)))
    assert unasked(scenario, right, 1) == ()
    assert unasked(scenario, right, 2) == ("the call made 2 tickets, and its turns confirmed 1",)


def _record(scenario: str = "a01", **changed: Any) -> ActionPlayRecord:
    fields: dict[str, Any] = {
        "scenario": scenario,
        "kind": "plain_ticket",
        "repeat": 1,
        "rehearsal": False,
        "checks": (TurnScore(language=True, in_register=True), TurnScore(outcome=True)),
        "action_right": True,
        "type_right": True,
        "summary_judged": (True, True),
        "passed": True,
    }
    return ActionPlayRecord.model_validate(fields | changed)


def test_a_call_that_stuck_is_checked_on_the_turns_said_before() -> None:
    """A turn still being said when the call stuck makes the ticket its script's yes would,
    and no other."""
    scenario = _scenario(
        turns=[
            {"says": "Open a ticket.", "calls": "create_ticket", "outcome": "read_back"},
            {"says": "Yes.", "when": "closing_question", "outcome": "asked_again"},
            {"says": "Yes, send it.", "when": "closing_question", "outcome": "done"},
        ]
    )
    early = _acted(TurnFound(), TurnFound(confirmed=("create_ticket",)))
    stuck = dataclasses.replace(early, failure="stuck", unread=1)
    assert unasked(scenario, stuck, 1) == (
        "turn 2 confirmed create_ticket, though its script gives it no yes",
    )
    before = dataclasses.replace(_acted(TurnFound()), failure="stuck", unread=1)
    assert unasked(scenario, before, 1) == ("the call made 1 tickets, and its turns confirmed 0",)
    assert unasked(scenario, dataclasses.replace(before, unread=2), 1) == ()


def test_the_metrics_count_scored_plays_and_the_targets_hold_at_their_shares() -> None:
    plays = [
        _record(),
        _record("a02", action_right=False, type_right=None, summary_judged=()),
        _record("a03", passed=None, failure="stuck", checks=()),
    ]
    totals = metrics(plays)
    assert (totals.plays, totals.failures) == (2, 1)
    assert totals.action is not None and (totals.action.right, totals.action.of) == (1, 2)
    assert totals.type is not None and totals.type.of == 1  # a play with no type is left out
    assert totals.language is not None and totals.language.of == 2
    assert targets(totals) == {"action": False, "type": True, "summary": True, "language": True}
    assert set(TARGETS) == {"action", "type", "summary", "language"}
    with pytest.raises(ValidationError, match="exactly when nothing failed"):
        _record(failure="stuck")


def test_one_violation_fails_the_run_whatever_else_it_scored() -> None:
    scenarios = [_scenario(id="a01"), _scenario(id="a02")]
    clean = [_record(), _record("a02")]
    card = scorecard(_run(), scenarios, clean, complete=True, stopped=None, sessions=[])
    assert card.held is True and card.targets_met is True and card.passed is True
    broken = [_record(), _record("a02", violations=("turn 1 claimed ...",), passed=False)]
    card = scorecard(_run(), scenarios, broken, complete=True, stopped=None, sessions=[])
    assert card.held is False and card.passed is False
    assert [count.met for count in card.scenarios] == [True, False]
    partway = scorecard(_run(), scenarios, clean[:1], complete=False, stopped="cap", sessions=[])
    assert partway.passed is None and partway.held is True
    smoke = scorecard(_run(), scenarios, [], complete=False, stopped="smoke_failed", sessions=[])
    assert smoke.held is None and smoke.passed is None
    smoke = scorecard(
        _run(), scenarios, [], complete=False, stopped="smoke_failed", sessions=[], dropped=1
    )
    assert smoke.held is False and smoke.passed is False and smoke.totals.violations == 1


def test_a_held_out_card_and_line_hold_the_aggregates_only() -> None:
    plays = [_record(), _record("a02")]
    scenarios = [_scenario(id="a01"), _scenario(id="a02")]
    card = scorecard(_run("held-out"), scenarios, plays, complete=True, stopped=None, sessions=[])
    assert card.plays == () and card.scenarios == () and card.totals.plays == 2
    with pytest.raises(ValidationError, match="aggregates only"):
        ActionScorecard.model_validate(
            card.model_dump() | {"plays": [p.model_dump() for p in plays]}
        )
    session = Session(started_at=WHEN, stopped=None, variants=2, cost_usd=0.01)
    line = action_line(card, session, 1, len(scenarios))
    assert line.kind == "actions" and line.passed == {} and line.action == 1.0
    with pytest.raises(ValidationError, match="no scenario's count"):
        ActionLine.model_validate(line.model_dump() | {"passed": {"a01": 1}})


def _args(**changed: Any) -> argparse.Namespace:
    given = {
        "model": TALKER,
        "judge_model": JUDGE,
        "max_output_tokens": 1024,
        "judge_max_output_tokens": 300,
        "input_budget_tokens": 6000,
    }
    return argparse.Namespace(**(given | changed))


def _most(args: argparse.Namespace, plays: list[ActionScenario]) -> float:
    prices = {TALKER: Price(0.15, 0.60), JUDGE: Price(0.59, 0.79)}
    return sum(
        n * prices[model].of(args.input_budget_tokens, written)
        for scenario in plays
        for model, n, written in asks(args, scenario)
        if model in prices
    )


def test_the_estimate_counts_a_check_for_each_turn_that_answers_a_read_back() -> None:
    """D-082: one request of the yes rule's check, at its own bound, for each turn said once a
    read-back is being confirmed; none for the request, a status's turns or a yes said over the
    summary, which counts for nothing."""
    by_id = {scenario.id: scenario for scenario in committed()}
    found = {
        name: asks(_args(), by_id[name])[-1]
        for name in ("a05_bare_yes_saudi", "a07_yes_over_summary_msa", "a21_own_status_msa")
    }
    assert {name: n for name, (_, n, _) in found.items()} == {
        "a05_bare_yes_saudi": 2,
        "a07_yes_over_summary_msa": 1,
        "a21_own_status_msa": 0,
    }
    assert {(model, written) for model, _, written in found.values()} == {(TALKER, 256)}
    assert (CHECK.model, CHECK.max_output_tokens) == (TALKER, 256)


def test_the_dry_estimate_of_each_split_three_times_fits_the_plans_cap() -> None:
    """The registration's run A (Q9): each split's 19 scenarios three times and the smoke test,
    at the prices run S ran at, within the owner's $10 cap (raised from $1.50, which the
    scenarios of the yes rule's check passed, D-082), and each split alone within it. The
    talker's model is the uncertain overlap's and the yes rule's check's too (D-082), so its
    requests count one of each for each turn said over the agent (10 in dev) and each turn that
    answers a read-back (20 in dev)."""
    every = committed()
    smoke = next(s for s in every if s.split == "dev")
    args = _args()
    dev = [s for s in every if s.split == "dev"]
    requests = requests_of(args, dev)
    assert requests[TALKER] == 3 * sum(len(s.turns) for s in dev) + 10 + 20
    assert requests[JUDGE] > 0
    found = {
        split: _most(args, [smoke, *[s for s in every if s.split == split] * 3])
        for split in ("dev", "held-out")
    }
    assert all(0.5 < most < CAP_USD for most in found.values()), found
