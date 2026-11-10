"""`ActionSafetySuite` (the design's 9.3) on Ole5's actions, `create_ticket` and `hand_off`, in
Saudi Arabic and English (plan 007's integration): each case a `TextCall` of Ole5's own talker
(`talker_agent`) over `FakeKnowledgeBase` and a fresh `MockTicketSystem` on a folder of the
test's own, on the library's talker, session, yes rule, guard and action runner over a
`MemoryOutbox`, the model a fake. The call's caller is the session's customer, as the token
route mints one (customer.py): every Ole5 action is refused before its read-back for a caller
who names no customer (invariant 3).

`add_ticket_note` has no suite here: its `validate` takes only a ticket this call's record
holds, and the suite starts each case on a fresh call, with no step that makes one first.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.tickets.drafts import CREATE_TICKET, HAND_OFF, HandoffDraft, TicketDraft
from ole5_voice.tickets.mock import MockTicketSystem
from pydantic import BaseModel
from t2_agentic_voice import Action, VoiceAgent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.evals import ActionSafetySuite, FakeKnowledgeBase

from tests.ole5_voice.tickets.action_support import caller as session_caller

# The report page shows no rows since this morning.
SAUDI_SUMMARY = "صفحة التقارير ما تطلع فيها أي بيانات من الصبح"
ENGLISH_SUMMARY = "The report page shows no rows since this morning."
# I want someone from support to look at the report page.
SAUDI_HANDOFF = "أبي أحد من الدعم يشوف صفحة التقارير"
ENGLISH_HANDOFF = "I want someone from support to look at the report page."


class TestCreateTicketIsSafe(ActionSafetySuite):
    """`create_ticket`, in English: a fresh mock for each case's agent, in the test's folder,
    and the session's customer as each call's `caller`."""

    language: LanguageTag | None = "en"
    caller = session_caller()

    @pytest.fixture(autouse=True)
    def _folders(self, tmp_path: Path) -> None:
        self._made = (tmp_path / f"mock-{n}" for n in itertools.count())

    def make_agent(self) -> VoiceAgent:
        """Ole5's talker over a fresh mock that answers: the suite's faults stand in for its
        write and its lookup where a case needs one."""
        tickets = MockTicketSystem(next(self._made))
        return talker_agent(FakeKnowledgeBase(), tickets=tickets)

    def action_under_test(self) -> Action:
        return own(self.make_agent(), CREATE_TICKET)

    def sample_draft(self) -> BaseModel:
        return TicketDraft(summary=ENGLISH_SUMMARY, type="Report", priority="High")


class TestCreateTicketIsSafeInSaudiArabic(TestCreateTicketIsSafe):
    """`create_ticket`, in Saudi Arabic, the summary in the caller's words."""

    language = "ar-SA"

    def sample_draft(self) -> BaseModel:
        return TicketDraft(summary=SAUDI_SUMMARY, type="Report", priority="High")


class TestHandOffIsSafe(TestCreateTicketIsSafe):
    """`hand_off`, in English."""

    def action_under_test(self) -> Action:
        return own(self.make_agent(), HAND_OFF)

    def sample_draft(self) -> BaseModel:
        return HandoffDraft(summary=ENGLISH_HANDOFF)


class TestHandOffIsSafeInSaudiArabic(TestHandOffIsSafe):
    """`hand_off`, in Saudi Arabic."""

    language = "ar-SA"

    def sample_draft(self) -> BaseModel:
        return HandoffDraft(summary=SAUDI_HANDOFF)


def own(agent: VoiceAgent, name: str) -> Action:
    """The agent's action named `name`."""
    (found,) = [t for t in agent.tools if isinstance(t, Action) and t.name == name]
    return found
