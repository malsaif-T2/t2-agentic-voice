"""The output guard (the design's 8.2): pure, with no IO, run on every clause the talker writes
before it goes to text-to-speech, and on a card's text before it is shown. The runtime's own
templates (greetings, notices, read-backs, `sending`, the outcome lines, progress lines, fixed
phrases) are never checked: their values come from the draft or the real result.

`check_clause` runs its two rules on a clause, in order; the live guard (agent/speech_guard.py)
and `TextCall`'s checks (testing/text_checks.py) both call it, so the order and each rule's
evidence are written here alone:

1. **Rule A, claims** (domain/claims.py): a claim phrase of an action needs that action in the
   call's record or a `reports_on` result, and each ID-shaped token of the clause a value of
   that evidence; a clause with no number is read by the earlier clauses of its reply the guard
   passed (D-081). Blocked: `unsupported_claim`. With no claim phrases (an agent that declares
   no action) it is not asked: nothing claims.
2. **Rule B, IDs** (domain/guard_ids.py): every ID-shaped token needs evidence seen this call,
   the record's and the status results' texts among it, so a claim rule A passed passes it too.
   Blocked: `unsupported_id`.

The verdict carries the reason as `ClauseBlocked` and `GuardBlocked` do (core/events.py's
`GuardReason`), the tokens with no support, which go to the talker's history as a developer note
and never to the caller, and the actions claimed. Rule C, the talker's text after an action
call, is dropped by the talker's turn (agent/turn.py), never blocked. `check_ids`, rule B alone,
is here too, for what reads no claims.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.events import GuardReason
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.claims import ActionEvidence, ClaimVerdict, check_claims
from t2_agentic_voice.domain.guard_ids import IdVerdict, check_ids

__all__ = ["GuardVerdict", "IdVerdict", "check_clause", "check_ids"]

_NO_CLAIMS: Mapping[str, Sequence[str]] = MappingProxyType({})


class GuardVerdict(BaseModel):
    """What the guard made of a clause: whether it `passed`; when not, why (`reason`) and the
    ID-shaped tokens it held with no support (`unsupported`), as normalized; and the actions
    its claim phrases named (`claimed`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    reason: GuardReason | None = None
    unsupported: tuple[str, ...] = ()
    claimed: tuple[str, ...] = ()


def check_clause(
    clause: str,
    *,
    evidence: Iterable[str],
    claims: Mapping[str, Sequence[str]] = _NO_CLAIMS,
    any_action: Sequence[str] = (),
    actions: Sequence[ActionEvidence] = (),
    settings: GuardSettings,
    year: int,
    earlier: Sequence[str] = (),
) -> GuardVerdict:
    """Rules A and B on `clause` (the module's docstring): `evidence`, the texts seen this call
    that may hold an ID (the tools' results, the caller's heard words); `claims`, each action's
    phrases, and `any_action`, the default ones with the settings' added (none of either for an
    agent with no action); `actions`, what supports claims about each action (its record and
    its `reports_on` results), which rule B counts as evidence too; `earlier`, the clauses of
    the same reply the guard passed before this one, in order, which rule A reads."""
    claim = ClaimVerdict(claimed=(), passed=True)
    if claims or any_action:
        claim = check_claims(
            clause,
            claims=claims,
            any_action=any_action,
            evidence=actions,
            settings=settings,
            year=year,
            earlier=earlier,
        )
    if not claim.passed:
        return GuardVerdict(
            passed=False,
            reason="unsupported_claim",
            unsupported=claim.unsupported,
            claimed=claim.claimed,
        )
    seen = [*evidence, *(text for each in actions for text in each.texts)]
    ids = check_ids(clause, evidence=seen, settings=settings, year=year)
    if not ids.passed:
        return GuardVerdict(
            passed=False,
            reason="unsupported_id",
            unsupported=ids.unsupported,
            claimed=claim.claimed,
        )
    return GuardVerdict(passed=True, claimed=claim.claimed)
