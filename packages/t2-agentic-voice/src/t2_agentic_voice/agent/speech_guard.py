"""The output guard on what the talker writes (the design's 8.2; docs/SECURITY.md, invariant 2):
rule A, then rule B, on each clause before it goes to text-to-speech, through domain/guard.py's
`check_clause`, and rule B on a card's text. Rule C, the text after an action call, is the
turn's (agent/turn.py): it is dropped before any clause of it reaches here.

- **Rule A, claims** (domain/claims.py's `check_claims`), only for an agent that declares an
  action or a tool that declares claims (`Tool.claims`; `claimants`): a rule added for actions
  goes only to an agent that declares one or a tool that writes. A tool's claims are held as an
  action's are, its results marked `done` its record (the results of its writes, `Memory.done`),
  so a clause that says its write was done passes only once one of them came in the call.
  An agent that declares no action, only such tools, is held to their phrases and the
  settings' `guard.claims`, never the library's defaults, which are an action's: their "has
  been booked" sits in an honest "nothing has been booked yet", and English negation is not
  read.
  A clause holding a claim phrase of an action (its `claims`) or one that claims any action
  (the library's default phrases, with the settings' `guard.claims`), every language's
  whatever the reply's, since a model may write a claim in another, passes only on that
  action's evidence: the results of its writes this call's record holds (each entry one only
  `actions` built, `is_recorded`), which back any claim about it; and the results that
  succeeded of the tools whose `reports_on` names it (agent/tool_calls.py's `Memory.reports`),
  when they hold an ID-shaped token, so a status that found nothing backs nothing. A status
  backs only a claim that names one of its numbers, or one with no number after a clause of
  this reply that named one (the owner's ruling, "Number or same reply", D-081): the guard
  keeps the clauses it passed in this reply, in order, for that. A clause it blocked was never
  said, so it is not kept. A passage, or any other tool's result, is no evidence of a claim. A
  clause it blocks is `unsupported_claim`.
- **Rule B, IDs** (domain/guard.py's `check_ids`): its evidence is every tool result of this
  call (passages included), the record's results and the caller's heard words, so a claim
  rule A passed, whose numbers are its action's, passes it too.

Both run on what the record and the tools hold as each clause comes, so a write that completes
during a reply is evidence from then on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain import claims as rule_a
from t2_agentic_voice.domain.action_declaration import Claims
from t2_agentic_voice.domain.completed_action import CompletedAction, is_recorded
from t2_agentic_voice.domain.guard import GuardVerdict, check_clause, check_ids


class Claimant(Protocol):
    """What rule A reads of an action, or of a tool that declares claims: its name and its
    claim phrases."""

    @property
    def name(self) -> str: ...

    @property
    def claims(self) -> Claims: ...


@dataclass(frozen=True)
class _ToolClaims:
    name: str
    claims: Claims


def claimants(actions: Sequence[Action], tools: Sequence[Tool]) -> tuple[Claimant, ...]:
    """What rule A holds to evidence: the agent's `actions`, then each of its `tools` that
    declares claims."""
    return (*actions, *(_ToolClaims(t.name, t.claims) for t in tools if t.claims is not None))


class SpeechGuard:
    """The guard of one reply (the module's docstring): `claimants`, the agent's actions and
    its tools that declare claims; `record`, the call's; `memory`, what its talker kept of its
    tools; `heard`, the caller's words so far."""

    def __init__(
        self,
        *,
        settings: GuardSettings,
        year: int,
        claimants: Sequence[Claimant],
        record: ActionRecord | None,
        memory: Memory,
        heard: Sequence[str],
    ) -> None:
        self.settings, self.year = settings, year
        self.claimants, self.record, self.memory = tuple(claimants), record, memory
        self.heard = heard
        self._phrases: tuple[dict[str, tuple[str, ...]], tuple[str, ...]] | None = None
        self._passed: list[str] = []  # the clauses of this reply the guard passed, in order

    def check(self, clause: str) -> GuardVerdict:
        """Rule A on `clause`, then rule B on one rule A passed, as domain/guard.py's verdict; a
        clause that passes is kept as said in this reply."""
        checked = self._checked(clause)
        if checked.passed:
            self._passed.append(clause)
        return checked

    @property
    def passed(self) -> tuple[str, ...]:
        """The clauses of this reply the guard passed, in order: those said, which the question
        limit reads (agent/question_limit.py)."""
        return tuple(self._passed)

    def _checked(self, clause: str) -> GuardVerdict:
        claims, any_action = self._claim_phrases() if self.claimants else ({}, ())
        return check_clause(
            clause,
            evidence=[*self.memory.evidence, *self.heard],
            claims=claims,
            any_action=any_action,
            actions=self.action_evidence(),
            settings=self.settings,
            year=self.year,
            earlier=tuple(self._passed),
        )

    def ids_pass(self, texts: Iterable[str]) -> bool:
        """Whether every text passes rule B (a card's)."""
        evidence = self.evidence()
        return all(
            check_ids(t, evidence=evidence, settings=self.settings, year=self.year).passed
            for t in texts
        )

    def evidence(self) -> list[str]:
        """Rule B's evidence: every tool result of the call, the record's, the heard words."""
        recorded = [text for entry in self._entries() for text in _texts(entry)]
        return [*self.memory.evidence, *recorded, *self.heard]

    def action_evidence(self) -> list[rule_a.ActionEvidence]:
        """Rule A's evidence, by action: its completed writes' results (the record's), and the
        results of the tools that report on it when they hold an ID-shaped token (a status's);
        and by a tool that declares claims, its results marked `done`, as a record's. One with
        none has none."""
        texts: dict[str, list[str]] = {}
        for entry in self._entries():
            texts.setdefault(entry.action, []).extend(_texts(entry))
        for tool, done in self.memory.done.items():
            texts.setdefault(tool, []).extend(done)
        found = [rule_a.ActionEvidence(action=a, texts=tuple(t)) for a, t in texts.items()]
        for action, reported in self.memory.reports.items():
            if rule_a.holds_an_id(reported, settings=self.settings, year=self.year):
                found.append(
                    rule_a.ActionEvidence(action=action, texts=tuple(reported), source="status")
                )
        return found

    def _entries(self) -> tuple[CompletedAction, ...]:
        """The record's entries now, each one only `actions` built."""
        if self.record is None:
            return ()
        return tuple(entry for entry in self.record.entries() if is_recorded(entry))

    def _claim_phrases(self) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
        """Each claimant's claim phrases, and those that claim any of them, every language's
        whatever the reply's, read once a reply: the library's defaults with the settings'
        added for an agent that declares an action, the settings' alone for one whose tools
        alone declare claims (the module's docstring)."""
        if self._phrases is None:
            claims = {a.name: rule_a.every_language(a.claims.phrases) for a in self.claimants}
            added = self.settings.claims
            acts = any(isinstance(a, Action) for a in self.claimants)
            general = rule_a.any_action_claims(added) if acts else rule_a.every_language(added)
            self._phrases = claims, general
        return self._phrases


def _texts(entry: CompletedAction) -> tuple[str, ...]:
    """What a record entry holds that a clause may say: its result whole, and its texts."""
    return (entry.result_json, *entry.evidence)
