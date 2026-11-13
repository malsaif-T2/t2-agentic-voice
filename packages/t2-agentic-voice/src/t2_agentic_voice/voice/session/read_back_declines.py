"""Which of the caller's turns declined an action's read-back, and how, for read_back.py's
`Confirming` (its module docstring's "What is heard over it" and "The answer"): each turn that
declined one, with the read-back's plan and the kind it was declined as (core/conversation.py's
`DeclineKind`), and each turn whose repeat request has it said again. A repeat request is kept
as both until the session says the read-back again (`again`), so a turn whose words are answered
instead still reaches the talker with the action declined, as a correction.
"""

from __future__ import annotations

from collections.abc import Callable

from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.yes_rule import plain_no
from t2_agentic_voice.domain.yes_words import ConsentWords


class Declines:
    """One call's declined read-backs, by the caller's turn (the module's docstring)."""

    def __init__(self) -> None:
        self._declined: dict[TurnId, tuple[ReadBackPlan, DeclineKind]] = {}
        self._again: dict[TurnId, ReadBackPlan] = {}  # each turn whose repeat request said again

    def add(self, turn_id: TurnId, plan: ReadBackPlan, kind: DeclineKind) -> None:
        """The caller's turn `turn_id` declined `plan`'s read-back, as `kind`."""
        self._declined[turn_id] = (plan, kind)

    def repeat(self, turn_id: TurnId, plan: ReadBackPlan) -> None:
        """The caller's turn `turn_id` asked to hear `plan`'s read-back again: declined by it,
        as a correction, until it is said again (`again`)."""
        self._again[turn_id] = plan
        self.add(turn_id, plan, "correction")

    def again(self, turn_id: TurnId) -> ReadBackPlan | None:
        """The read-back the caller's turn `turn_id` asked to hear again, to say now, no longer
        declined by it; None when it asked for none."""
        plan = self._again.pop(turn_id, None)
        if plan is not None:
            self._declined.pop(turn_id, None)
        return plan

    def answered(self, turn_id: TurnId) -> bool:
        """The caller's turn `turn_id` is answered, its words handed to the talker: whether it
        had asked to hear a read-back again, not said again (it stays declined, a correction)."""
        return self._again.pop(turn_id, None) is not None

    def holds(self, turn_id: TurnId) -> bool:
        """Whether the caller's turn `turn_id` declined a read-back."""
        return turn_id in self._declined

    def told(
        self, turn_id: TurnId, *, words: str, consent: Callable[[ReadBackPlan], ConsentWords]
    ) -> DeclinedAction | None:
        """The action the caller's turn `turn_id`, its words `words`, declined, as the talker
        learns of it; None when it declined none. A correction whose words are a plain no by the
        yes rule's lists for its plan (`consent`; domain/yes_rule.py's `plain_no`) is told as a
        `no`: a cancel said over the summary, or in the gap before its first audio (the yes
        rule's own corrections always hold a word that is no plain no's)."""
        found = self._declined.get(turn_id)
        if found is None:
            return None
        plan, kind = found
        if kind == "correction" and plain_no(words, consent(plan)):
            kind = "no"
        return DeclinedAction(action=plan.action, kind=kind, words=words)

    def end(self) -> None:
        """The call ended: nothing is said again."""
        self._again.clear()
