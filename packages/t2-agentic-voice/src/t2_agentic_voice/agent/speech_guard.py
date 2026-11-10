"""The output guard on what the talker writes (the design's 8.2; docs/SECURITY.md, invariant 2):
rule A, then rule B, on each clause before it goes to text-to-speech, and rule B on a card's
text. Rule C, the text after an action call, is the turn's (agent/turn.py): it is dropped before
any clause of it reaches here.

- **Rule A, claims** (domain/claims.py's `check_claims`), for an agent that declares actions
  only: a rule added for actions goes only to an agent that declares one (plan 007's baseline).
  A clause holding a claim phrase of an action (its `claims`) or one that claims any action
  (the library's default phrases, with the settings' `guard.claims`), every language's
  whatever the reply's, since a model may write a claim in another, passes only on that
  action's evidence: the results of its writes this call's record holds (each entry one only
  `actions` built, `is_recorded`), and the results that succeeded of the tools whose
  `reports_on` names it (agent/tool_calls.py's `Memory.reports`), when they hold an ID-shaped
  token, so a status that found nothing backs nothing. A passage, or any other tool's result,
  is no evidence of a claim. A clause it blocks is `unsupported_claim`.
- **Rule B, IDs** (domain/guard.py's `check_ids`), on a clause that claims nothing: its
  evidence is every tool result of this call (passages included), the record's results and
  the caller's heard words.

Both run on what the record and the tools hold as each clause comes, so a write that completes
during a reply is evidence from then on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.core.events import GuardReason
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain import claims as rule_a
from t2_agentic_voice.domain.completed_action import CompletedAction, is_recorded
from t2_agentic_voice.domain.guard import check_ids


@dataclass(frozen=True, slots=True)
class Checked:
    """What the guard made of a clause: whether it `passed`, and when not, by which rule
    (`reason`) and the ID-shaped tokens it held with no support (`unsupported`)."""

    passed: bool
    reason: GuardReason = "unsupported_id"
    unsupported: tuple[str, ...] = ()


class SpeechGuard:
    """The guard of one reply (the module's docstring): `actions`, the agent's; `record`, the
    call's; `memory`, what its talker kept of its tools; `heard`, the caller's words so far."""

    def __init__(
        self,
        *,
        settings: GuardSettings,
        year: int,
        actions: Sequence[Action],
        record: ActionRecord | None,
        memory: Memory,
        heard: Sequence[str],
    ) -> None:
        self.settings, self.year = settings, year
        self.actions, self.record, self.memory, self.heard = tuple(actions), record, memory, heard
        self._phrases: tuple[dict[str, tuple[str, ...]], tuple[str, ...]] | None = None

    def check(self, clause: str) -> Checked:
        """Rule A on `clause`, then rule B on one that claims nothing."""
        if self.actions:
            claims, any_action = self._claim_phrases()
            verdict = rule_a.check_claims(
                clause,
                claims=claims,
                any_action=any_action,
                evidence=self.action_evidence(),
                settings=self.settings,
                year=self.year,
            )
            if not verdict.passed:
                return Checked(False, "unsupported_claim", verdict.unsupported)
            if verdict.claimed:
                return Checked(True)
        ids = check_ids(clause, evidence=self.evidence(), settings=self.settings, year=self.year)
        return Checked(ids.passed, "unsupported_id", ids.unsupported)

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
        """Rule A's evidence, by action: its completed writes' results, and the results of the
        tools that report on it when they hold an ID-shaped token. An action with neither has
        none."""
        texts: dict[str, list[str]] = {}
        for entry in self._entries():
            texts.setdefault(entry.action, []).extend(_texts(entry))
        for action, reported in self.memory.reports.items():
            if rule_a.holds_an_id(reported, settings=self.settings, year=self.year):
                texts.setdefault(action, []).extend(reported)
        return [rule_a.ActionEvidence(action=a, texts=tuple(t)) for a, t in texts.items() if t]

    def _entries(self) -> tuple[CompletedAction, ...]:
        """The record's entries now, each one only `actions` built."""
        if self.record is None:
            return ()
        return tuple(entry for entry in self.record.entries() if is_recorded(entry))

    def _claim_phrases(self) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
        """Each action's claim phrases, and those that claim any action, every language's
        whatever the reply's, read once a reply."""
        if self._phrases is None:
            claims = {a.name: rule_a.every_language(a.claims.phrases) for a in self.actions}
            self._phrases = claims, rule_a.any_action_claims(self.settings.claims)
        return self._phrases


def _texts(entry: CompletedAction) -> tuple[str, ...]:
    """What a record entry holds that a clause may say: its result whole, and its texts."""
    return (entry.result_json, *entry.evidence)
