"""`ActionSafetySuite` (the design's 9.3) on the minimal example's action, `request_callback`
(examples/minimal's callback.py), in English and in Saudi Arabic: every case a `TextCall` of the
callback helper, on the library's own talker, session, yes rule, guard and action runner over a
`MemoryOutbox`, the model a fake (plan 007's integration)."""

from __future__ import annotations

from minimal_example.callback import CallbackDesk, CallbackRequest, make_callback_helper
from pydantic import BaseModel
from t2_agentic_voice import Action, VoiceAgent
from t2_agentic_voice.evals import ActionSafetySuite

# "Talabi ma waSal": my order did not arrive.
SAUDI_REASON = "طلبي ما وصل"


class TestRequestCallbackIsSafe(ActionSafetySuite):
    """The callback, in English: a fresh desk for each case's agent."""

    def make_agent(self) -> VoiceAgent:
        return make_callback_helper(CallbackDesk())

    def action_under_test(self) -> Action:
        (found,) = [t for t in self.make_agent().tools if isinstance(t, Action)]
        return found

    def sample_draft(self) -> BaseModel:
        return CallbackRequest(branch="olaya", reason="my order did not arrive")


class TestRequestCallbackIsSafeInSaudiArabic(TestRequestCallbackIsSafe):
    """The callback, in Saudi Arabic, the reason in the caller's words."""

    language = "ar-SA"

    def sample_draft(self) -> BaseModel:
        return CallbackRequest(branch="olaya", reason=SAUDI_REASON)
