"""What one turn of a `TextCall` did with an action (testing/text_call.py; plan 007), each check
raising AssertionError with what the turn did instead, for `TurnExpectations`
(testing/text_turn.py): the drafts it read back, the ask-again it said, the action its words
confirmed, and how that action's write ended, its `sending` line said and then its outcome's.

**What the agent said after a turn** is read from every reply asked for from the moment the
turn's speech began until the caller's next turn began (an outcome, spoken at a turn boundary,
from then to the call's end), each clause played, cut, or still to play in a reply no stop cut:
a read-back or an ask-again is the session's own reply, which may answer no turn. A failure
names the action, the turn and the fields that differ, never a draft's value or the caller's
words (GP-19).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import JsonValue

from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.testing.text_read_back import fold, forms, readings, templates
from t2_agentic_voice.testing.text_reads import TextReads
from t2_agentic_voice.testing.text_watch import JobRun, plans_of


def _span(reads: TextReads, turn_id: int, *, onward: bool) -> range:
    """The replies asked for from turn `turn_id`'s speech on (the module's docstring)."""
    said = reads.said.get(turn_id)
    start = 0 if said is None else said.first_reply
    later = [s.first_reply for s in reads.said.values() if s.turn_id > turn_id]
    end = reads.session.playback.next_id if onward or not later else min(later)
    return range(start, end)


def _said(reads: TextReads, span: range) -> dict[tuple[int, int], str]:
    """The captions said in the replies of `span`, by reply and clause, in order."""
    playback, found = reads.session.playback, {}
    for reply in reads.session.history.replies():
        played = playback.reply(reply.reply_id)
        if reply.reply_id not in span or played is None:
            continue
        for index, clause in enumerate(reply.clauses):
            if clause.fate != "unplayed" or not played.cut:
                found[(reply.reply_id, index)] = clause.text
    return found


def _folded(reads: TextReads, turn_id: int, *, onward: bool = False) -> str:
    return "".join(
        fold(text) for text in _said(reads, _span(reads, turn_id, onward=onward)).values()
    )


def _draft(plan_json: str) -> dict[str, JsonValue]:
    parsed = json.loads(plan_json)
    return parsed if isinstance(parsed, dict) else {}


def _differs(draft: Mapping[str, JsonValue], values: Mapping[str, JsonValue]) -> list[str]:
    return sorted(name for name, value in values.items() if draft.get(name) != value)


def read_back(reads: TextReads, turn_id: int) -> tuple[ReadBackPlan, ...]:
    """The drafts whose summary the agent said whole after turn `turn_id`, in order."""
    span = _span(reads, turn_id, onward=False)
    said = _said(reads, span)
    found = readings(reads.session.playback, plans_of(reads.watched))
    return tuple(
        r.plan
        for r in found
        if r.reply_id in span and all((r.reply_id, i) in said for i in r.summary)
    )


def expect_read_back(
    reads: TextReads, turn_id: int, contains: str | None, values: Mapping[str, JsonValue]
) -> None:
    plans = read_back(reads, turn_id)
    if not plans:
        raise AssertionError(f"turn {turn_id} read no draft back")
    for plan in plans:
        texts = f"{plan.summary.text} {plan.question.text}"
        if (contains is None or contains in texts) and not _differs(
            _draft(plan.draft_json), values
        ):
            return
    named = [(p.action, _differs(_draft(p.draft_json), values)) for p in plans]
    raise AssertionError(
        f"turn {turn_id} read back no draft holding the text and values given: it read back "
        f"{named} (each action with the fields that differ)"
    )


def expect_no_read_back(reads: TextReads, turn_id: int) -> None:
    plans = read_back(reads, turn_id)
    if plans:
        raise AssertionError(f"turn {turn_id} read back {[p.action for p in plans]}")


def expect_asked_again(reads: TextReads, turn_id: int) -> None:
    folded = _folded(reads, turn_id)
    for plan in plans_of(reads.watched):
        if any(form in folded for form in forms(plan.asked_again, plan.language)):
            return
    raise AssertionError(f"turn {turn_id} was not asked again")


def own_lines(reads: TextReads) -> frozenset[str]:
    """The folded forms of the runtime's own lines the call may have said so far
    (text_read_back's `templates`): each read-back's lines, and each outcome's in its
    language."""
    runs = () if reads.jobs is None else reads.jobs.runs
    outcomes = [(r.outcome.line, r.given["language"]) for r in runs if r.outcome is not None]
    return templates(plans_of(reads.watched), outcomes)


def confirmed_by(reads: TextReads, turn_id: int) -> tuple[JobRun, ...]:
    """The jobs the words of turn `turn_id` confirmed, in the order they began."""
    runs = () if reads.jobs is None else reads.jobs.runs
    return tuple(run for run in runs if run.confirmed.turn_id == turn_id)


def _job(reads: TextReads, turn_id: int, name: str, values: Mapping[str, JsonValue]) -> JobRun:
    runs = confirmed_by(reads, turn_id)
    for run in runs:
        draft = _draft(run.confirmed.draft_json)
        if run.confirmed.action == name and not _differs(draft, values):
            return run
    made = [(r.confirmed.action, _differs(_draft(r.confirmed.draft_json), values)) for r in runs]
    raise AssertionError(
        f"turn {turn_id} confirmed no {name} holding the values given: it confirmed {made} "
        "(each action with the fields that differ)"
    )


def expect_confirmed(
    reads: TextReads, turn_id: int, name: str, values: Mapping[str, JsonValue]
) -> None:
    _job(reads, turn_id, name, values)


def expect_no_action(reads: TextReads, turn_id: int) -> None:
    runs = confirmed_by(reads, turn_id)
    if runs:
        raise AssertionError(f"turn {turn_id} confirmed {[r.confirmed.action for r in runs]}")


def expect_ended(reads: TextReads, turn_id: int, name: str, kind: OutcomeKind) -> None:
    """The write of `name` turn `turn_id` confirmed ended as `kind`, and the agent said its
    `sending` line, then the outcome's line."""
    run = _job(reads, turn_id, name, {})
    outcome = run.outcome
    if outcome is None:
        raise AssertionError(f"turn {turn_id}'s {name} has not ended")
    if outcome.kind != kind:
        raise AssertionError(f"turn {turn_id}'s {name} ended {outcome.kind}, not {kind}")
    language = run.given["language"]
    plans = [p for p in plans_of(reads.watched) if p.draft_json == run.confirmed.draft_json]
    folded = _folded(reads, turn_id, onward=True)
    sending = [folded.find(f) for p in plans for f in forms(p.sending, p.language) if f in folded]
    if not sending:
        raise AssertionError(f"turn {turn_id}'s {name} was never said to be sending")
    after = folded[min(sending) :]
    if not any(form in after for form in forms(outcome.line, language)):
        raise AssertionError(f"turn {turn_id}'s {name} ended {kind}, its line never said after")
