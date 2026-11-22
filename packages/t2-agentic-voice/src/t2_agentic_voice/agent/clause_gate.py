"""The gate each whole clause of one reply passes before it is said, and each card before it is
shown (agent/turn.py's "Speech as it is written" and "Questions"): a clause the stray-script
filter left with nothing to say is none; one that asks the caller a question past
`guard.questions_per_reply`, or comes after one, is dropped unsaid (agent/question_limit.py);
every other goes through the output guard (agent/speech_guard.py) and is `SpokenClause` or
`ClauseBlocked`. A blocked clause counts, leaves a developer note for the next turn's history
(agent/context.py's `BLOCKED` or `CLAIM_BLOCKED`), and by `guard.on_block` stops the rest of the
reply (`stopped`, for `drop_rest`) or goes alone. Under `guard.plain_speech` (D-111) a clause
that is not speech is never said, nor anything of its request after it (`not_speech`, which
agent/turn.py reads), and every other is said with the invisible and markdown marks taken out
(agent/plain_speech.py). A card passes only when rule B passes each of its texts; one that does
not is logged by its tool's name alone. Each clause, spoken or blocked, carries the reply's tag,
but under `tts.voice_by_script` an Arabic clause of an English reply carries the agent's Arabic
tag (agent/clause_voice.py), the caller's register with it.

**A clause sent again** (`guard.retry_claims`; the owner's call of 2026-11-18, where an agent
whose booking tool had refused said «تم حجز رحلتك», your trip is booked, and a guard that held
it back would have left the error notice in its place; and `guard.retry_ids`, from the owner's
calls of 2026-11-22, where a model that added two fares itself after a tool failed had its sum
blocked by rule B, and the caller heard the error notice): a clause that rule A blocks under
the first, or rule B under the second, leaves no note and no notice (`ClauseBlocked.sent_again`);
nothing more of its request is said nor any tool of it run (`held`, which agent/turn.py reads),
and the request is sent once more, one past the turn's limit, with what it said before the
clause as the model's own words and its rule's note (`held_back`: `CLAIM_HELD` or `ID_HELD`), up
to `guard.retries_per_turn` times a turn (`retries`, the two rules' together). A clause blocked
once those are spent, or by a rule whose setting is off, goes as `guard.on_block` says, and the
session says the fixed phrase in its place (voice/session/talker_play.py).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.agent.clause_voice import ClauseVoice
from t2_agentic_voice.agent.context import BLOCKED, CLAIM_BLOCKED
from t2_agentic_voice.agent.events import ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.agent.plain_speech import is_speech, spoken
from t2_agentic_voice.agent.question_limit import QuestionLimit
from t2_agentic_voice.agent.speech_guard import Claimant, SpeechGuard
from t2_agentic_voice.agent.stray_script import StrayScript
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import ChatMessage
from t2_agentic_voice.domain.text.arabic_numbers import Register

_log = get_logger(__name__)
# What a request sent again after a clause held back reads, by the rule that held it: a claim
# (rule A), or a number no result gives (rule B); the module's docstring.
CLAIM_HELD = (
    "Note: the output guard held back the rest of your answer, unspoken, from a sentence that "
    "said something was done: no result of this call says it was done. Go on from what the "
    "caller heard, saying only what the results say: nothing is done until a result says so."
)
ID_HELD = (
    "Note: the output guard held back the rest of your answer, unspoken, from a sentence holding "
    "a number that no result of this call gives. Go on from what the caller heard, with only the "
    "numbers the results give: never work a number out yourself (a sum, a difference); call the "
    "tool that gives it."
)


class ClauseGate:
    """The gate of one reply in `language`, the turn `turn_id`'s (the module's docstring); the
    guard reads the `claimants` (the agent's actions and its tools that declare claims), the
    call's `record`, the talker's `memory` and the caller's `heard` words, and `scripts` is the
    reply's stray-script filter; each Arabic clause carries the caller's `register`, and an
    Arabic clause of an English reply the `arabic` tag when one is given (agent/clause_voice.py's
    `arabic_tag`)."""

    def __init__(
        self,
        *,
        settings: GuardSettings,
        year: int,
        language: LanguageTag,
        turn_id: TurnId,
        claimants: Sequence[Claimant],
        record: ActionRecord | None,
        memory: Memory,
        heard: Sequence[str],
        scripts: StrayScript,
        register: Register | None = None,
        arabic: LanguageTag | None = None,
    ) -> None:
        self.settings, self.turn_id = settings, turn_id
        self.voice = ClauseVoice(language, arabic)  # each clause's tag (agent/clause_voice.py)
        self.register = register
        self.memory, self.scripts = memory, scripts
        self.guard = SpeechGuard(
            settings=settings,
            year=year,
            claimants=claimants,
            record=record,
            memory=memory,
            heard=heard,
        )
        self.questions = QuestionLimit(settings.questions_per_reply)
        self.stopped = False  # a blocked clause dropped the rest of the reply
        self.blocked = 0
        self.not_speech = False  # a clause not speech ended the request (D-111)
        self.held = False  # a clause held back ended the request, which is sent again
        self.retries = 0  # the turn's requests sent again so (`guard.retries_per_turn`)
        self.note = CLAIM_HELD  # the note of the last clause held back
        self.said_now = 0  # the clauses the request said so far

    @property
    def ended(self) -> bool:
        """Whether nothing more of the request is said: a clause not speech, or one held."""
        return self.not_speech or self.held

    def begin(self) -> None:
        """A new request of the reply begins: nothing of it said, nor found not speech, nor a
        clause held back."""
        self.not_speech, self.held, self.said_now = False, False, 0

    def held_back(self) -> list[ChatMessage]:
        """What the request sent again after a clause held back reads after the turn's
        messages: what its request said before the clause, as the model's own, then its rule's
        note (`CLAIM_HELD` or `ID_HELD`)."""
        passed = self.guard.passed
        said = passed[len(passed) - self.said_now :]
        own = [ChatMessage.assistant(" ".join(said))] if said else []
        return [*own, ChatMessage.system(self.note)]

    def _again(self, claim: bool) -> bool:
        """Whether a clause blocked for a claim (`claim`) or for a number is held back and its
        request sent again: its rule's setting on, and a retry of the turn's left."""
        on = self.settings.retry_claims if claim else self.settings.retry_ids
        return on and self.retries < self.settings.retries_per_turn

    def said(self, clauses: Iterable[str]) -> list[TalkerEvent]:
        """`clauses`, each spoken once the guard passed it, or blocked, or dropped past the
        reply's question limit (the module's docstring)."""
        events: list[TalkerEvent] = []
        for text in clauses:
            if self.stopped or self.ended:
                break
            if self.settings.plain_speech:  # D-111
                self.not_speech = not is_speech(text)
                if self.not_speech:
                    break
                text = spoken(text)
            if self.scripts.changed and not any(char.isalnum() for char in text):
                continue  # the filter left it nothing to say: never a clause said as silence
            if self.questions.drops(text, said=self.guard.passed):
                continue  # a question past the reply's limit, or a clause after one: unsaid
            checked = self.guard.check(text)
            tag = self.voice.of(text)
            if checked.passed:
                register = None if tag == "en" else self.register
                events.append(SpokenClause(text=text, language=tag, caller_register=register))
                self.said_now += 1
                continue
            self.blocked += 1
            claim = checked.reason == "unsupported_claim"
            again = self._again(claim)
            if not again:  # a clause sent again is answered anew: no note of it
                self.memory.notes[self.turn_id] = CLAIM_BLOCKED if claim else BLOCKED
            events.append(
                ClauseBlocked(
                    text=text,
                    language=tag,
                    unsupported=checked.unsupported,
                    reason=checked.reason or "unsupported_id",
                    sent_again=again,
                )
            )
            if again:
                self.held, self.retries = True, self.retries + 1
                self.note = CLAIM_HELD if claim else ID_HELD
                break
            self.stopped = self.settings.on_block == "drop_rest"
        return events

    def shown(self, card: Card, tool: str) -> bool:
        """Whether `card`'s text passes the guard; a card that does not is not shown, and is
        logged by its tool's name alone."""
        if self.guard.ids_pass(card.texts()):
            return True
        _log.warning("talker_card_blocked", turn_id=self.turn_id, tool=tool)
        return False
