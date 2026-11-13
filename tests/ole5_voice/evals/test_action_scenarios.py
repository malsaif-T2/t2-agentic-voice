"""Plan 007's action scenarios (ole5_voice/evals/action_scenarios.py; the plan's "The
measurement, registered before any result"): the committed 49 break no rule, each of the 24
kinds (the plan's 15, four of answers the yes rule's lists leave unplaced, D-082, a note on a
ticket made in the call, the owner's ruling of 2026-11-10, and four of a read-back dropped, the
owner's answer of 2026-11-11) in dev and in held-out, held-out in a language its dev scenarios
are not, every language in each split; the four of a read-back dropped split and said as that
answer registered them; and each rule shown to catch a made-up scenario that breaks it. No
scenario is played here (test_action_play.py plays each)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.action_scenarios import (
    ACTIONS_DIR,
    KINDS,
    RULES,
    ActionScenario,
    load_action_scenarios,
    problems,
)
from ole5_voice.evals.items import EVALS, GoldenSetError, load_items
from ole5_voice.tickets.values import TYPES
from pydantic import ValidationError

COMMITTED = load_action_scenarios(EVALS / ACTIONS_DIR)


def test_the_committed_scenarios_break_no_rule() -> None:
    assert len(COMMITTED) == 49 and len(KINDS) == 24
    assert problems(COMMITTED) == []
    assert set(RULES) == set(KINDS)


def test_each_kind_is_split_across_two_languages() -> None:
    """Split by scenario before any run (the plan): each kind in dev and in held-out, one
    scenario of each but a question in answer to a read-back, which has two in dev (English and
    Saudi, the owner's answer of 2026-11-11), so held-out shows each kind in a language dev did
    not."""
    for kind in KINDS:
        dev = [s.language for s in COMMITTED if s.kind == kind and s.split == "dev"]
        held = [s.language for s in COMMITTED if s.kind == kind and s.split == "held-out"]
        assert len(dev) == (2 if kind == "question_to_read_back" else 1), kind
        assert len(held) == 1 and held[0] not in dev, kind


# The owner's answer of 2026-11-11 ("Fix all, then run A"): each scenario of a read-back
# dropped, its split, and its second turn, the one that drops it: when it is said (None: once
# the read-back played) and what follows it.
DROPPED = {
    "a41_question_to_read_back_english": ("dev", None, "talker"),
    "a42_question_to_read_back_saudi": ("dev", None, "talker"),
    "a43_question_to_read_back_msa": ("held-out", None, "talker"),
    "a44_cancel_for_another_english": ("dev", None, "read_back"),
    "a45_cancel_for_another_saudi": ("held-out", None, "read_back"),
    "a46_cancel_over_summary_english": ("held-out", "read_back", "talker"),
    "a47_cancel_over_summary_saudi": ("dev", "read_back", "talker"),
    "a48_stop_over_summary_saudi": ("dev", "read_back", "stopped"),
    "a49_stop_over_summary_msa": ("held-out", "read_back", "stopped"),
}


def test_a_read_back_dropped_is_split_and_said_as_the_owners_answer_registered_it() -> None:
    """A question or a request for another ticket said once the read-back played, a cancel or
    «خلاص» (khalas, enough) said over its summary: each after a ticket's read-back, nothing
    made but the other ticket the caller asks for, read back anew and made on a yes."""
    by_id = {scenario.id: scenario for scenario in COMMITTED}
    for name, (split, when, outcome) in DROPPED.items():
        found = by_id[name]
        first, dropping = found.turns[:2]
        assert (found.split, dropping.when, dropping.outcome) == (split, when, outcome), name
        assert first.calls == "create_ticket" and first.outcome == "read_back", name
        assert found.made == (1 if outcome == "read_back" else 0), name
    assert {by_id[name].turns[1].says for name in DROPPED if "stop" in name} == {"خلاص"}


def test_the_tickets_made_hold_a_type_and_summary_facts_to_judge() -> None:
    """The targets on held-out: the right type ≥ 0.85, the summary faithful ≥ 0.85."""
    made = [s for s in COMMITTED if s.made]
    assert len([s for s in made if s.split == "held-out"]) >= 8
    assert all(s.ticket_type in TYPES and s.summary_facts for s in made)
    assert len({s.ticket_type for s in made}) >= 7


def test_no_scenario_number_is_one_of_the_golden_sets() -> None:
    """The scenarios' ticket numbers are their own, not the golden set's readings."""
    golden = " ".join(
        text for item in load_items(EVALS / "golden") for text in (item.text, *item.alternatives)
    )
    for scenario in COMMITTED:
        numbers = [t.number for t in scenario.seed]
        assert all(number not in golden for number in numbers), scenario.id


def _valid(**changed: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "made_up",
        "kind": "plain_ticket",
        "split": "dev",
        "language": "en",
        "notes": "A made-up scenario.",
        "made": 1,
        "ticket_type": "Bug",
        "turns": [
            {"says": "Open a made-up ticket.", "calls": "create_ticket", "outcome": "read_back"},
            {"says": "Yes, send it.", "outcome": "done", "says_number": "whole"},
        ],
    }
    return fields | changed


def _of(**changed: Any) -> list[str]:
    """The problems of one made-up scenario, those of the set as a whole left out."""
    made = ActionScenario.model_validate(_valid(**changed))
    return [problem for problem in problems([made]) if problem.startswith(f"{made.id}: ")]


def test_a_valid_scenario_has_no_problem_of_its_own() -> None:
    assert _of() == []


@pytest.mark.parametrize(
    ("changed", "found"),
    [
        ({"kind": "refusal", "made": 0, "ticket_type": None}, "mode refuse"),
        ({"tickets_mode": "late"}, "mode answer"),
        ({"made": 0, "ticket_type": None}, "makes 1 tickets"),
        ({"ticket_type": None}, "ticket_type is given exactly"),
        ({"passage": "A made-up passage, number 2026110482000555."}, "only the fake number's"),
        ({"noted": 1}, "its kind adds 0 notes"),
        ({"kind": "ticket_note"}, "its kind adds 1 notes"),
        ({"kind": "ticket_note", "noted": 1}, "no turn calls add_ticket_note"),
        (
            {
                "turns": [
                    {"says": "Yes.", "when": "closing_question", "outcome": "done"},
                ]
            },
            "the first turn follows no reply",
        ),
        (
            {
                "turns": [
                    {"says": "Open one.", "calls": "create_ticket", "outcome": "read_back"},
                    {"says": "Yes.", "when": "tool_running", "cuts_reply": True},
                ]
            },
            "cuts a reply only when said over it",
        ),
        (
            {
                "turns": [
                    {"says": "Open one.", "search": True},
                    {"says": "Yes.", "outcome": "done"},
                ]
            },
            "nothing is being confirmed",
        ),
        (
            {
                "turns": [
                    {"says": "Open one.", "calls": "ticket_status", "outcome": "read_back"},
                    {"says": "Yes.", "outcome": "done"},
                ]
            },
            "a read-back follows only an action's call",
        ),
        (
            {
                "turns": [
                    {"says": "Open one.", "calls": "create_ticket", "outcome": "read_back"},
                    {"says": "Yes."},
                    {"says": "Yes, send it.", "outcome": "done"},
                ]
            },
            "expects nothing of its reply",
        ),
        (
            {
                "turns": [
                    {"says": "Open one.", "calls": "create_ticket", "outcome": "read_back"},
                    {"says": "Umm.", "outcome": "asked_again"},
                    {"says": "Yes, send it.", "when": "closing_question", "outcome": "done"},
                ]
            },
            "only the ask-again line plays",
        ),
    ],
)
def test_each_rule_catches_a_scenario_that_breaks_it(changed: dict[str, Any], found: str) -> None:
    assert any(found in problem for problem in _of(**changed)), _of(**changed)


def test_the_status_kinds_need_their_tickets() -> None:
    status = {"kind": "own_status", "made": 0, "ticket_type": None}
    turn = [{"says": "How are my tickets?", "calls": "ticket_status"}]
    assert any("no ticket made through the agent" in p for p in _of(**status, turns=turn))
    other = {
        "owner": "other",
        "number": "2026110582000012",
        "type": "Bug",
        "status": "Open",
        "summary": "A made-up ticket.",
    }
    others = {"kind": "others_status", "made": 0, "ticket_type": None, "seed": [other]}
    asked = [{"says": "How is ticket 9999?", "language": "en"}]
    assert any("another customer's ticket number" in p for p in _of(**others, turns=asked))
    said = [{"says": "How is ticket 0012?", "language": "en"}]
    assert _of(**others, turns=said) == []
    forged = {**others, "seed": [{**other, "through_agent": True}]}
    assert any("never made through" in p for p in _of(**forged, turns=said))


NOTE_TURNS: list[dict[str, Any]] = [
    {"says": "Open a ticket.", "calls": "create_ticket", "outcome": "read_back"},
    {"says": "Yes, send it.", "outcome": "done", "says_number": "whole"},
    {"says": "Add a note to it.", "calls": "add_ticket_note", "outcome": "read_back"},
    {"says": "Yes, send it.", "outcome": "done"},
]


def test_a_note_goes_only_on_a_ticket_the_call_made_before_it() -> None:
    """As `add_ticket_note` takes only a ticket this call's record holds (tickets/actions.py):
    its call follows a turn whose ticket's write was done, never one before the ticket or after
    a ticket that was not made."""
    note = {"kind": "ticket_note", "noted": 1}
    assert _of(**note, turns=NOTE_TURNS) == []
    early = [NOTE_TURNS[2], NOTE_TURNS[3], NOTE_TURNS[0], NOTE_TURNS[1]]
    assert "made_up: turn 1: a note goes only on a ticket made earlier in the call" in _of(
        **note, turns=early
    )
    refused = [NOTE_TURNS[0], {"says": "No.", "outcome": "talker"}, *NOTE_TURNS[2:]]
    assert any("turn 3: a note goes only on a ticket made" in p for p in _of(**note, turns=refused))


def test_the_set_needs_each_kind_in_both_splits_and_each_language_in_each() -> None:
    one = ActionScenario.model_validate(_valid())
    found = problems([one, one])
    assert "the scenario 'made_up' twice" in found
    assert any("'eager_yes' is in no split" in problem for problem in found)
    assert "held-out has no scenario in ar" in found
    assert any(problem.startswith("the rehearsal's scenarios are") for problem in found)


def test_a_scenario_file_is_read_strictly(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError, match="no such folder"):
        load_action_scenarios(tmp_path / "none")
    written = (EVALS / ACTIONS_DIR / "a01_plain_ticket_saudi.toml").read_text(encoding="utf-8")
    (tmp_path / "a99_other.toml").write_text(written, encoding="utf-8")
    held = r"^a99_other.toml: holds the scenario 'a01_plain_ticket_saudi', not 'a99_other'$"
    with pytest.raises(GoldenSetError, match=held):
        load_action_scenarios(tmp_path)
    with pytest.raises(ValidationError):
        ActionScenario.model_validate(_valid(confirmed=True))
    with pytest.raises(ValidationError):
        ActionScenario.model_validate(_valid(ticket_type="Complaint"))
