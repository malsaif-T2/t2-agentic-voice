"""The output guard's rule A (the design's 8.2): a clause that holds a claim phrase of an action
passes only if the call's record holds that action or a `reports_on` tool returned it, and every
ID-shaped token in the clause is then a value of that result, never a passage's. Rule C, the
talker's text after an action call, is state on the talker's turn (agent/turn.py), not a rule
of the clause. Pure, and matched on the guard's normalized text.

Plan 007's Track A fills `check_claims` and `default_claims`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.words import LanguageCode


@dataclass(frozen=True, slots=True)
class ActionEvidence:
    """What supports claims about one `action`: the texts of its completed results and of the
    results of the `reports_on` tools that report on it."""

    action: str
    texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    """What rule A made of a clause: the actions it `claimed`, whether it `passed`, and when
    not, the ID-shaped tokens it held with no support (`unsupported`), as normalized."""

    claimed: tuple[str, ...]
    passed: bool
    unsupported: tuple[str, ...] = ()


def default_claims(code: LanguageCode) -> tuple[str, ...]:
    """The short list of phrases that claim any action, in the language `code`."""
    raise NotImplementedError(f"plan 007's Track A fills default_claims ({code})")


def check_claims(
    clause: str,
    *,
    claims: Mapping[str, Sequence[str]],
    any_action: Sequence[str],
    evidence: Sequence[ActionEvidence],
    settings: GuardSettings,
    year: int,
) -> ClaimVerdict:
    """Rule A on `clause`, as the module says: `claims` maps each action to its phrases in the
    clause's language and `any_action` holds the default ones."""
    raise NotImplementedError(f"plan 007's Track A fills check_claims ({len(clause)} characters)")
