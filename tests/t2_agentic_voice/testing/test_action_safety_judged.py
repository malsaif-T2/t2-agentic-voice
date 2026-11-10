"""`ActionSafetySuite` (testing/action_safety.py, testing/action_judged.py) on an agent that has a
chat model judge the answers the yes rule's lists leave unplaced (D-082), in English and in Saudi
Arabic: every case of the suite, its judged cases' rails among them, a `TextCall` of the
end-to-end calls' agent (action_call_support.py) on the library's own talker, session, yes rule
and its check, guard and action runner. The same suite on an agent that does not ask, the
minimal example's, passes its judged cases at once (tests/minimal_example)."""

from __future__ import annotations

from pydantic import BaseModel
from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.evals import ActionSafetySuite

from tests.t2_agentic_voice.testing.action_call_support import ACTION, SAUDI, Backend, agent_of
from tests.t2_agentic_voice.testing.action_support import Visit


class TestBookVisitIsSafeWhenTheModelJudges(ActionSafetySuite):
    """`book_visit`, in English, for an agent that asks: a fresh backend for each case."""

    def make_agent(self) -> VoiceAgent:
        return agent_of(Backend(), asks=True)

    def action_under_test(self) -> Action:
        (found,) = [
            t for t in self.make_agent().tools if isinstance(t, Action) and t.name == ACTION
        ]
        return found

    def sample_draft(self) -> BaseModel:
        return Visit(room="R-204", note="the projector is broken")


class TestBookVisitIsSafeWhenTheModelJudgesInSaudiArabic(TestBookVisitIsSafeWhenTheModelJudges):
    """`book_visit`, in Saudi Arabic, the note in the caller's words."""

    language = "ar-SA"

    def sample_draft(self) -> BaseModel:
        return Visit(room="R-204", note=SAUDI.note)


def test_an_agent_that_does_not_ask_passes_the_judged_cases_at_once() -> None:
    class NotAsking(TestBookVisitIsSafeWhenTheModelJudges):
        def make_agent(self) -> VoiceAgent:
            return agent_of(Backend())

    suite = NotAsking()
    assert not suite._scene().asks
    suite.test_an_unlisted_yes_once_the_question_ended_confirms_once()  # no call is made
