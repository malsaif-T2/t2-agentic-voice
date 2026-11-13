"""The gate each whole clause of one reply passes before it is said, and each card before it is
shown (agent/turn.py's "Speech as it is written" and "Questions"): a clause the stray-script
filter left with nothing to say is none; one that asks the caller a question past
`guard.questions_per_reply`, or comes after one, is dropped unsaid (agent/question_limit.py);
every other goes through the output guard (agent/speech_guard.py) and is `SpokenClause` or
`ClauseBlocked`. A blocked clause counts, leaves a developer note for the next turn's history
(agent/context.py's `BLOCKED` or `CLAIM_BLOCKED`), and by `guard.on_block` stops the rest of the
reply (`stopped`, for `drop_rest`) or goes alone. A card passes only when rule B passes each of
its texts; one that does not is logged by its tool's name alone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.agent.context import BLOCKED, CLAIM_BLOCKED
from t2_agentic_voice.agent.events import ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.agent.question_limit import QuestionLimit
from t2_agentic_voice.agent.speech_guard import SpeechGuard
from t2_agentic_voice.agent.stray_script import StrayScript
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card

_log = get_logger(__name__)


class ClauseGate:
    """The gate of one reply in `language`, the turn `turn_id`'s (the module's docstring); the
    guard reads `actions`, the call's `record`, the talker's `memory` and the caller's `heard`
    words, and `scripts` is the reply's stray-script filter."""

    def __init__(
        self,
        *,
        settings: GuardSettings,
        year: int,
        language: LanguageTag,
        turn_id: TurnId,
        actions: Sequence[Action],
        record: ActionRecord | None,
        memory: Memory,
        heard: Sequence[str],
        scripts: StrayScript,
    ) -> None:
        self.settings, self.language, self.turn_id = settings, language, turn_id
        self.memory, self.scripts = memory, scripts
        self.guard = SpeechGuard(
            settings=settings,
            year=year,
            actions=actions,
            record=record,
            memory=memory,
            heard=heard,
        )
        self.questions = QuestionLimit(settings.questions_per_reply)
        self.stopped = False  # a blocked clause dropped the rest of the reply
        self.blocked = 0

    def said(self, clauses: Iterable[str]) -> list[TalkerEvent]:
        """`clauses`, each spoken once the guard passed it, or blocked, or dropped past the
        reply's question limit (the module's docstring)."""
        events: list[TalkerEvent] = []
        for text in clauses:
            if self.stopped:
                break
            if self.scripts.changed and not any(char.isalnum() for char in text):
                continue  # the filter left it nothing to say: never a clause said as silence
            if self.questions.drops(text, said=self.guard.passed):
                continue  # a question past the reply's limit, or a clause after one: unsaid
            checked = self.guard.check(text)
            if checked.passed:
                events.append(SpokenClause(text=text, language=self.language))
                continue
            self.blocked += 1
            claim = checked.reason == "unsupported_claim"
            self.memory.notes[self.turn_id] = CLAIM_BLOCKED if claim else BLOCKED
            events.append(
                ClauseBlocked(
                    text=text,
                    language=self.language,
                    unsupported=checked.unsupported,
                    reason=checked.reason,
                )
            )
            self.stopped = self.settings.on_block == "drop_rest"
        return events

    def shown(self, card: Card, tool: str) -> bool:
        """Whether `card`'s text passes the guard; a card that does not is not shown, and is
        logged by its tool's name alone."""
        if self.guard.ids_pass(card.texts()):
            return True
        _log.warning("talker_card_blocked", turn_id=self.turn_id, tool=tool)
        return False
