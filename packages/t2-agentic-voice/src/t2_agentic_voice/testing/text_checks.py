"""The checks every `TextCall` runs (testing/text_call.py; the design's 8.2, 8.3 and 9.2): what the
caller heard of the talker's own words, each clause checked as the output guard checks it, and
what the yes rule let through, so `call.violations` says what a guard or a rule let pass.

- **Rule B** (domain/guard.py, plan 006): every ID-shaped token a clause holds has evidence,
  the caller's words, the tools' results, the cards and the record of completed actions.
- For an agent that declares an action (plan 007), and only then, so an agent with none is
  checked as before:
  - **Rule A** (domain/claims.py): a clause that claims an action is backed by the record or
    by a result of a tool that `reports_on` it, every ID it holds a value of that result.
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

import json

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.agent.events import ReadBackRequested, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.claims import ActionEvidence, check_claims, default_claims
from t2_agentic_voice.domain.completed_action import CompletedAction
from t2_agentic_voice.domain.guard import check_ids
from t2_agentic_voice.domain.yes_rule import is_confirmed
from t2_agentic_voice.testing.text_read_back import (
    is_template,
    readings,
    summary_played_at,
    templates,
)
from t2_agentic_voice.testing.text_reads import TextReads
from t2_agentic_voice.testing.text_turn import TextTurn
from t2_agentic_voice.testing.text_watch import actions_of, plans_of
from t2_agentic_voice.testing.turn_data import HeardClause


def _own(reads: TextReads) -> frozenset[str]:
    """The folded forms of the runtime's own lines the call may have said."""
    runs = () if reads.jobs is None else reads.jobs.runs
    outcomes = [(r.outcome.line, r.given["language"]) for r in runs if r.outcome is not None]
    return templates(plans_of(reads.watched), outcomes)


def _heard(reads: TextReads) -> list[tuple[int, HeardClause]]:
    """The talker's clauses the caller heard, each with its turn, but the runtime's own."""
    own = _own(reads)
    return [
        (turn_id, clause)
        for turn_id in reads.said
        for clause in TextTurn(reads, turn_id).clauses
        if not clause.phrase and clause.fate != "unplayed" and not is_template(clause.text, own)
    ]


def _completed(reads: TextReads) -> tuple[CompletedAction, ...]:
    """The record's entries; none before a job ran, since only a job adds to it."""
    runs = () if reads.jobs is None else reads.jobs.runs
    return () if reads.record is None or not runs else reads.record.entries()


def _rule_b(reads: TextReads, heard: list[tuple[int, HeardClause]], *, year: int) -> list[str]:
    settings = reads.session.setup.settings.guard
    evidence = [said.text for said in reads.said.values()]
    evidence += list(reads.runner.evidence if reads.runner is not None else ())
    for turn_id in reads.said:
        for card in TextTurn(reads, turn_id).cards:
            evidence += [card.title, *card.steps, *([card.source] if card.source else [])]
    evidence += [text for done in _completed(reads) for text in done.evidence]
    found = []
    for turn_id, clause in heard:
        verdict = check_ids(clause.text, evidence=evidence, settings=settings, year=year)
        if not verdict.passed:
            tokens = ", ".join(verdict.unsupported)
            found.append(f"turn {turn_id} said {tokens} with no evidence: {clause.text!r}")
    return found


def _evidence(reads: TextReads) -> list[ActionEvidence]:
    """What backs a claim about each action: its completed results, and the results of the
    tools that report on it."""
    found = [
        ActionEvidence(action=done.action, texts=(*done.evidence, done.result_json))
        for done in _completed(reads)
    ]
    runner = reads.runner
    if runner is None:
        return found
    for request, result in runner.calls.values():
        tool = runner.tool(request.name)
        if tool is None or result is None or not result.ok:
            continue
        texts = (*result.evidence, json.dumps(result.data, ensure_ascii=False))
        found += [ActionEvidence(action=name, texts=texts) for name in tool.reports_on]
    return found


def _rule_a(
    reads: TextReads, heard: list[tuple[int, HeardClause]], actions: tuple[Action, ...], year: int
) -> list[str]:
    settings: VoiceSettings = reads.session.setup.settings
    evidence = _evidence(reads)
    found = []
    for turn_id, clause in heard:
        tag = clause.language
        code: LanguageCode = "en" if tag == "en" else "ar"
        claims = {a.name: a.claims.for_language(tag) for a in actions if a.claims.covers(tag)}
        any_action = (*default_claims(code), *settings.guard.claims.get(code, ()))
        verdict = check_claims(
            clause.text,
            claims=claims,
            any_action=any_action,
            evidence=evidence,
            settings=settings.guard,
            year=year,
        )
        if not verdict.passed:
            what = ", ".join(verdict.claimed) or "an action"
            found.append(f"turn {turn_id} claimed {what} with no record: {clause.text!r}")
    return found


def _rule_c(reads: TextReads) -> list[str]:
    found: list[str] = []
    own = _own(reads)
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
