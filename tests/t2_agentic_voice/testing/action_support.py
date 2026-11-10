"""What the tests of `TextCall`'s actions and of `ActionSafetySuite` share (plan 007, Track D): a
made-up action over a made-up desk, an agent that declares it, the read-back the session would
play for it, a `ConfirmedAction` and a record entry built through their seals as only the yes
rule and the record build them, and stand-ins for the parts other tracks fill (the claims of
Track A, the jobs of Track B), each patched in the test that needs it alone.

A test's scripted talker keeps each plan from the session (`read_back_steps`, text_call_support's
`Asked`) and says the plan's lines as clauses: the session plays them as it plays any clause,
captioned as written, which is how the text call finds a read-back's parts, and never starts
confirming, so a test's yes goes to the talker, and the tests hold before and after Track C's
session reads a read-back back itself."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, Field
from t2_agentic_voice.actions.action import Action, ActionContext, HeardConsent, action
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain import claims as rule_a
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.claims import ActionEvidence, ClaimVerdict
from t2_agentic_voice.domain.completed_action import RECORD_SEAL, CompletedAction
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome, OutcomeKind
from t2_agentic_voice.domain.yes_rule import CONFIRMED_SEAL, ConfirmedAction
from t2_agentic_voice.testing import text_checks

from tests.t2_agentic_voice.testing.text_call_support import Asked, Step

CLAIM = "request is booked"


class Visit(BaseModel):
    room: Annotated[str, Field(pattern=r"^R-[0-9]{3}$")]
    note: Annotated[str, Field(min_length=1, max_length=80)]


class Booked(BaseModel):
    number: str


@dataclass
class Desk:
    """A made-up desk: each booking by its request ID."""

    booked: dict[str, Visit] = field(default_factory=dict)

    def book(self, request_id: str, visit: Visit) -> Booked:
        self.booked.setdefault(request_id, visit)
        return Booked(number=str(5100 + len(self.booked)))


def book_action(desk: Desk) -> Action:
    @action(
        description="Book a visit to a room.",
        read_back=ReadBack(
            {
                "en": ("I'll book room {room:id} for: {note}.", "Shall I send it?"),
                "ar": ("room {room:id}: {note}.", "send?"),
            }
        ),
        done=Say(en="Done, number {number:id}.", ar="done {number:id}."),
        claims=Claims({"en": [CLAIM], "ar": ["booked"]}),
    )
    async def book_visit(ctx: ActionContext, draft: Visit) -> Booked:
        return desk.book(ctx.request_id, draft)

    return book_visit


def agent_with(desk: Desk | None = None, *, tools: Sequence[Any] = ()) -> VoiceAgent:
    return VoiceAgent(
        name="action-test",
        languages=[Language.english(greeting="Hello."), Language.saudi_arabic(greeting="هلا.")],
        instructions="Book visits.",
        tools=[book_action(desk or Desk()), *tools],
    )


VISIT = Visit(room="R-204", note="the projector is broken")


def line(text: str) -> SpokenLine:
    return SpokenLine(text=text, spoken=text)


def plan_of(visit: Visit = VISIT, *, call_id: str = "t-1") -> ReadBackPlan:
    return ReadBackPlan(
        action="book_visit",
        tool_call_id=call_id,
        draft_json=visit.model_dump_json(),
        summary=SpokenLine(
            text=f"I'll book room {visit.room} for: {visit.note}.",
            spoken=f"I'll book room R 2 0 4 for: {visit.note}.",
        ),
        question=line("Shall I send it?"),
        asked_again=line("Sorry, shall I send it, yes or no?"),
        declined=line("All right, I won't send it."),
        sending=line("One moment, I'm booking it."),
        language="en",
        max_attempts=2,
    )


def read_back_steps(plan: ReadBackPlan) -> list[Step]:
    """The plan asked for, kept from the session, then its lines said as clauses (the module's
    docstring)."""
    return [
        Asked(plan),
        SpokenClause(text=plan.summary.text, language=plan.language),
        SpokenClause(text=plan.question.text, language=plan.language),
        ReplyDone(),
    ]


def confirmed(
    plan: ReadBackPlan, *, turn_id: int, speech_at: float, words: str = "yes send it"
) -> ConfirmedAction:
    values = {
        "action": plan.action,
        "draft_json": plan.draft_json,
        "reply_id": 1,
        "turn_id": turn_id,
        "words": words,
        "source": "typed",
        "speech_at": speech_at,
    }
    return ConfirmedAction.model_validate(values, context=CONFIRMED_SEAL)


def completed(*, number: str = "5101") -> CompletedAction:
    values = {
        "action": "book_visit",
        "request_id": "r-1",
        "result_json": Booked(number=number).model_dump_json(),
        "evidence": (number,),
        "at": 1.0,
    }
    return CompletedAction.model_validate(values, context=RECORD_SEAL)


def context(request_id: str = "r-1") -> ActionContext:
    return ActionContext(
        caller=Caller(subject="u-1"),
        call_id="c-1",
        language="en",
        request_id=request_id,
        consent=HeardConsent(words="yes", source="typed", speech_at=1.0),
    )


@dataclass
class FakeJobs:
    """The part that acts, as Track B fills it: each job ends as `kind`, with `line`."""

    kind: OutcomeKind = "done"
    line: SpokenLine = field(default_factory=lambda: line("Done, number 5101."))
    ran: list[ConfirmedAction] = field(default_factory=list)

    async def run(
        self,
        confirmed: ConfirmedAction,
        *,
        caller: Caller,
        call_id: str,
        language: LanguageTag,
        turn_id: int,
        conversation: tuple[ConversationLine, ...],
        clock: Clock,
        wording: LanguageTag | None = None,
    ) -> ActionOutcome:
        self.ran.append(confirmed)
        await asyncio.sleep(0)
        return ActionOutcome(
            action=confirmed.action, request_id="r-1", kind=self.kind, line=self.line
        )


@dataclass
class Claimed:
    """A stand-in for Track A's rule A: a clause holding a phrase of `claims` or `any_action`
    passes only when an evidence of that action holds every number the clause holds."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def check(
        self,
        clause: str,
        *,
        claims: Mapping[str, Sequence[str]],
        any_action: Sequence[str],
        evidence: Sequence[ActionEvidence],
        settings: GuardSettings,
        year: int,
        earlier: Sequence[str] = (),
    ) -> ClaimVerdict:
        self.calls.append(
            {"clause": clause, "claims": claims, "any_action": any_action, "evidence": evidence}
        )
        lowered = clause.casefold()
        named = [
            a for a, phrases in claims.items() if any(p.casefold() in lowered for p in phrases)
        ]
        if any(phrase.casefold() in lowered for phrase in any_action):
            named = named or list(claims)
        numbers = [w.strip(".,") for w in clause.split() if w.strip(".,").isdigit()]
        backed = [
            e
            for e in evidence
            if e.action in named and all(n in " ".join(e.texts) for n in numbers)
        ]
        return ClaimVerdict(claimed=tuple(named), passed=not named or bool(backed))


def stand_in_record(
    monkeypatch: pytest.MonkeyPatch, entries: tuple[CompletedAction, ...] = ()
) -> None:
    """Track B's record of completed actions, stood in for in this test alone."""
    monkeypatch.setattr(ActionRecord, "entries", lambda self: entries)


def stand_in_claims(monkeypatch: pytest.MonkeyPatch) -> Claimed:
    """Track A's claim rule, stood in for in this test alone."""
    claimed = Claimed()
    monkeypatch.setattr(text_checks, "check_claims", claimed.check)
    monkeypatch.setattr(rule_a, "default_claims", lambda code: ("i've booked",))
    return claimed
