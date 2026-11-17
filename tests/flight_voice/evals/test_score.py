"""What a run of the flight agent's scripted calls keeps (flight_voice/evals/score.py): a scenario
passes when every check holds in at least two of its three plays, `all_plays` says whether every
play held, violations are counted per play and break the hard constraint whatever passed, a
scenario that needs a capability that does not play yet is skipped, a smoke play is never
scored, a record keeps each turn's tool calls as sent and the clauses the guard blocked (an older
record, kept without them, still loads), and the session's history line is one the library's day
counter reads."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flight_voice.evals.call import PlayRead, TurnRead
from flight_voice.evals.folder import append_line, card_md
from flight_voice.evals.history import history_line
from flight_voice.evals.scenarios import load
from flight_voice.evals.score import (
    PlayRecord,
    RunInfo,
    Session,
    needed,
    record_of,
    scorecard,
)
from pydantic import JsonValue
from t2_agentic_voice.evals import ModelSpend, TextToolCall, requests_today

BEGAN = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
SCENARIOS = {s.id: s for s in load()}
F01, F09 = SCENARIOS["f01_round_trip_saudi"], SCENARIOS["f09_switch_ar_to_en"]
INFO = RunInfo(
    name="f-dev-1",
    started_at=BEGAN,
    commit="a" * 40,
    split="dev",
    model="openai/gpt-oss-120b",
    effort="medium",
    repeats=3,
    cap_usd=10.0,
    input_budget_tokens=8000,
    estimate_usd=0.2,
    prices={},
    limits={},
    data=(F01.id, F09.id),
)


def _record(passed: bool, repeat: int, *, violations: int = 0, smoke: bool = False) -> PlayRecord:
    return PlayRecord(
        scenario=F01.id,
        repeat=repeat,
        smoke=smoke,
        passed=passed,
        failed=() if passed else ("outcome@4", "said_any@1"),
        violations=("rule A",) * violations,
        seconds=1.0,
    )


def test_two_passing_plays_of_three_pass_and_all_plays_says_whether_each_held() -> None:
    assert [needed(n) for n in (1, 2, 3, 6)] == [1, 2, 2, 4]
    card = scorecard(
        INFO,
        [(F01, ()), (F09, ("language_switch",))],
        [_record(True, 1), _record(False, 2), _record(True, 3), _record(False, 0, smoke=True)],
        stopped=None,
        sessions=[],
    )
    f01, f09 = card.scenarios
    assert (f01.plays, f01.passes, f01.passed, f01.all_plays) == (3, 2, True, False)
    assert f01.failed == {"outcome": 1, "said_any": 1}
    assert f09.skipped == ("language_switch",) and f09.passed is None
    assert card.complete and card.held
    assert (card.totals.played, card.totals.passed, card.totals.skipped) == (1, 1, 1)
    shown = card_md(card)
    assert "| f01_round_trip_saudi | 3 | 2 | passed | no |" in shown
    assert "skipped (language_switch)" in shown


def test_one_passing_play_fails_and_a_scenario_short_of_its_plays_is_unfinished() -> None:
    lost_plays = [_record(True, 1), _record(False, 2), _record(False, 3)]
    lost = scorecard(INFO, [(F01, ())], lost_plays, stopped=None, sessions=[])
    assert lost.scenarios[0].passed is False
    short = scorecard(INFO, [(F01, ())], [_record(True, 1)], stopped="cap", sessions=[])
    assert short.scenarios[0].passed is None and not short.complete


def test_a_violation_in_any_play_breaks_the_hard_constraint_and_is_counted_per_play() -> None:
    records = [_record(True, 1), _record(True, 2, violations=2), _record(True, 3)]
    card = scorecard(INFO, [(F01, ())], records, stopped=None, sessions=[])
    assert not card.held and card.scenarios[0].violations == (0, 2, 0)
    assert card.totals.violations == 2


def test_a_record_names_each_failed_check_with_its_turn_and_never_a_text() -> None:
    read = PlayRead(turns=(None,) * len(F01.turns), violations=())
    record = record_of(F01, 1, read, 2.5)
    assert not record.passed and record.failed[:2] == ("booked", "said@1")
    assert all(turn.heard == "" for turn in record.turns)


def test_a_record_keeps_each_call_as_sent_and_the_clauses_the_guard_blocked() -> None:
    depart: dict[str, JsonValue] = {"kind": "relative", "when": "tomorrow"}
    sent: dict[str, JsonValue] = {"destination": "Doha", "depart": depart}
    call = TextToolCall(call_id="c1", tool="search_flights", arguments=sent, outcome="ok", ms=4.0)
    blocked = ("Your booking reference is 482913.",)
    turn = TurnRead(
        index=0,
        fate="answered",
        clauses=(),
        heard=(),
        tools=(call,),
        cards=0,
        blocked=1,
        blocked_texts=blocked,
    )
    read = PlayRead(turns=(turn, *(None,) * (len(F01.turns) - 1)), violations=())
    record = record_of(F01, 1, read, 2.5)
    kept = record.turns[0]
    assert kept.tools == ("search_flights",)
    assert [(c.tool, c.arguments) for c in kept.calls] == [("search_flights", sent)]
    assert kept.blocked_texts == blocked
    assert PlayRecord.model_validate_json(record.model_dump_json()) == record


def test_a_record_kept_without_the_calls_and_the_blocked_clauses_still_loads() -> None:
    old = (
        '{"scenario": "f01_round_trip_saudi", "repeat": 1, "passed": false, "failed": '
        '["args@3"], "seconds": 2.0, "turns": [{"heard": "Okay.", "own": "Okay.", "tools": '
        '["search_flights"], "fate": "answered"}]}'
    )
    (turn,) = PlayRecord.model_validate_json(old).turns
    assert turn.tools == ("search_flights",) and turn.calls == () and turn.blocked_texts == ()


def test_the_history_line_is_one_the_days_counter_reads(tmp_path: Path) -> None:
    spent = ModelSpend(model="openai/gpt-oss-120b", requests=12, cost_usd=0.01)
    session = Session(started_at=BEGAN, commit="a" * 40, plays=3, spend=(spent,), cost_usd=0.01)
    played = [_record(True, n) for n in (1, 2, 3)]
    card = scorecard(INFO, [(F01, ())], played, stopped=None, sessions=[session])
    history = tmp_path / "history.jsonl"
    append_line(history, history_line(card, session, 1))
    assert requests_today([history], BEGAN.date()) == {"openai/gpt-oss-120b": 12}
    assert history.read_bytes().endswith(b"}\n") and b"\r" not in history.read_bytes()
