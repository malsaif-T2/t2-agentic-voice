"""The checks every `TextCall` runs (testing/text_call.py; the design's 8.2, 8.3 and 9.2): what the
caller heard of the talker's own words, each clause checked as the output guard checks it, and
what the yes rule let through, so `call.violations` says what a guard or a rule let pass.

- **Rule B** (domain/guard.py, plan 006): every ID-shaped token a clause holds has evidence,
  the caller's words, the tools' results (their data and evidence texts), what an action's call
  gave back (its read-back's note or its refusal), the cards and the record of completed
  actions, as the output guard reads them.
- For an agent that declares an action (plan 007), and only then, so an agent with none is
  checked as before:
  - **Rule A** (domain/claims.py), through the guard's `check_clause` (domain/guard.py), as the
    live guard runs it: a clause that claims an action, in any language's phrases, is backed
    by the record or by a result of a tool that `reports_on` it holding an ID-shaped token,
    every ID it holds a value of that result. A status backs it only when it names one of the
    status's numbers, or names none after an earlier clause of the same reply named one, a
    clause the guard would have passed, as the guard keeps the clauses it passed
    (agent/speech_guard.py). A turn's talker reply is one reply: the talker answers each turn
    once, and its other replies (a read-back, an outcome) are the runtime's lines, not
    checked.
  - **Rule C**: once the talker asked for a read-back, it spoke no more words of its own in
    that turn.
  - **The yes rule**: every action the session confirmed was confirmed by words begun once a
    read-back of its own draft had played whole, that summary unbroken.

A clause the caller never heard, a fixed phrase, and a line of the runtime's own (a read-back,
an ask-again, `declined`, `sending`, an outcome) are not checked: the guard never checks a
template (testing/text_read_back.py). A finding names the turn and the rule, and holds the
talker's clause, never the caller's words or a draft's values (GP-19).
"""

from __future__ import annotations

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.agent_tools import actions_of
from t2_agentic_voice.agent.events import ReadBackRequested, SpokenClause, ToolEnded
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.claims import (
    ActionEvidence,
    any_action_claims,
    every_language,
    holds_an_id,
)
from t2_agentic_voice.domain.completed_action import CompletedAction
from t2_agentic_voice.domain.guard import check_clause, check_ids
from t2_agentic_voice.domain.yes_rule import is_confirmed
from t2_agentic_voice.testing.text_actions import own_lines
from t2_agentic_voice.testing.text_read_back import is_template, readings, summary_played_at
from t2_agentic_voice.testing.text_reads import TextReads
from t2_agentic_voice.testing.text_turn import TextTurn
from t2_agentic_voice.testing.text_watch import plans_of
from t2_agentic_voice.testing.turn_data import HeardClause


def _heard(reads: TextReads) -> list[tuple[int, HeardClause]]:
    """The talker's clauses the caller heard, each with its turn, but the runtime's own."""
    return [
        (turn_id, clause)
        for turn_id in reads.said
        for clause in TextTurn(reads, turn_id).clauses
        if not clause.phrase and not clause.template and clause.fate != "unplayed"
    ]


def _completed(reads: TextReads) -> tuple[CompletedAction, ...]:
    """The record's entries; none before a job ran, since only a job adds to it."""
    runs = () if reads.jobs is None else reads.jobs.runs
    return () if reads.record is None or not runs else reads.record.entries()


def _action_results(reads: TextReads) -> list[str]:
    """What each action's call gave back to the model, its data as JSON, which the talker keeps
    as a tool's (agent/tool_calls.py): the calls no tool runner ran."""
    ran = set() if reads.runner is None else set(reads.runner.calls)
    talks = [] if reads.watched is None else list(reads.watched.talks.values())
    return [
        event.result
        for talk in talks
        for _, event in talk.events
        if isinstance(event, ToolEnded) and event.call_id not in ran and event.result
    ]


def _id_evidence(reads: TextReads) -> list[str]:
    """Rule B's evidence: the caller's words, the tools' results, what an action's call gave
    back, the cards and the record, as the guard reads them."""
    evidence = [said.text for said in reads.said.values()]
    evidence += list(reads.runner.evidence if reads.runner is not None else ())
    evidence += _action_results(reads)
    for turn_id in reads.said:
        for card in TextTurn(reads, turn_id).cards:
            evidence += card.texts()
    # A completed action's result whole and its texts, as the guard reads the record
    # (agent/speech_guard.py).
    evidence += [text for done in _completed(reads) for text in (done.result_json, *done.evidence)]
    return evidence


def _rule_b(reads: TextReads, heard: list[tuple[int, HeardClause]], *, year: int) -> list[str]:
    settings = reads.session.setup.settings.guard
    evidence = _id_evidence(reads)
    found = []
    for turn_id, clause in heard:
        verdict = check_ids(clause.text, evidence=evidence, settings=settings, year=year)
        if not verdict.passed:
            tokens = ", ".join(verdict.unsupported)
            found.append(f"turn {turn_id} said {tokens} with no evidence: {clause.text!r}")
    return found


def _evidence(reads: TextReads, *, year: int) -> list[ActionEvidence]:
    """What backs a claim about each action: its completed results (the record's), and the
    results of the tools that report on it that hold an ID-shaped token (a status's), as the
    guard reads them."""
    found = [
        ActionEvidence(action=done.action, texts=(*done.evidence, done.result_json))
        for done in _completed(reads)
    ]
    runner, settings = reads.runner, reads.session.setup.settings.guard
    if runner is None:
        return found
    for request, result in runner.calls.values():
        tool = runner.tool(request.name)
        if tool is None or result is None or not result.ok:
            continue
        texts = result.texts()
        if holds_an_id(texts, settings=settings, year=year):
            found += [
                ActionEvidence(action=name, texts=texts, source="status")
                for name in tool.reports_on
            ]
    return found


def _rule_a(
    reads: TextReads, heard: list[tuple[int, HeardClause]], actions: tuple[Action, ...], year: int
) -> list[str]:
    settings: VoiceSettings = reads.session.setup.settings
    evidence, ids = _evidence(reads, year=year), _id_evidence(reads)
    # Every language's phrases, whatever the clause's, as the guard reads them.
    claims = {a.name: every_language(a.claims.phrases) for a in actions}
    any_action = any_action_claims(settings.guard.claims)
    found = []
    passed: dict[int, list[str]] = {}  # each turn's reply: the clauses the guard would pass
    for turn_id, clause in heard:
        earlier = passed.setdefault(turn_id, [])
        verdict = check_clause(
            clause.text,
            evidence=ids,
            claims=claims,
            any_action=any_action,
            actions=evidence,
            settings=settings.guard,
            year=year,
            earlier=tuple(earlier),
        )
        if verdict.reason == "unsupported_claim":
            what = ", ".join(verdict.claimed) or "an action"
            found.append(f"turn {turn_id} claimed {what} with no record: {clause.text!r}")
        elif verdict.passed:  # kept as the guard keeps a clause it passed
            earlier.append(clause.text)
    return found


def _rule_c(reads: TextReads) -> list[str]:
    found: list[str] = []
    own = own_lines(reads)
    talks = [] if reads.watched is None else list(reads.watched.talks.values())
    for talk in talks:
        asked = False
        for _, event in talk.events:
            asked = asked or isinstance(event, ReadBackRequested)
            if asked and isinstance(event, SpokenClause) and not is_template(event.text, own):
                said = f"turn {talk.turn_id}'s talker spoke after its action call"
                found.append(f"{said}: {event.text!r}")
    return found


def _yes_rule(reads: TextReads) -> list[str]:
    playback, found = reads.session.playback, list[str]()
    every = readings(playback, plans_of(reads.watched))
    for run in [] if reads.jobs is None else reads.jobs.runs:
        confirmed = run.confirmed
        turn, name = confirmed.turn_id, confirmed.action
        if not is_confirmed(confirmed):
            found.append(f"turn {turn}'s {name} ran with no yes the yes rule issued")
            continue
        mine = (name, confirmed.draft_json)
        own = [r for r in every if (r.plan.action, r.plan.draft_json) == mine]
        ended = [at for r in own if (at := summary_played_at(playback, r)) is not None]
        if not any(at <= confirmed.speech_at for at in ended):
            found.append(
                f"turn {turn}'s yes to {name} began before a read-back of its draft played whole"
            )
    return found


def call_violations(reads: TextReads, *, year: int) -> tuple[str, ...]:
    """What the call's checks found so far (the module's docstring), each said in words."""
    heard = _heard(reads)
    found = _rule_b(reads, heard, year=year)
    actions = actions_of(reads.session.setup.agent)
    if actions:
        found += _rule_a(reads, heard, actions, year)
        found += _rule_c(reads)
        found += _yes_rule(reads)
    return tuple(found)
