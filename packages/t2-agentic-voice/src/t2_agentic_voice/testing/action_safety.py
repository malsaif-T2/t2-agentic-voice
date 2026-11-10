"""`ActionSafetySuite` (the design's 9.3): the adversarial cases any team's action must pass, as a
base class a team's tests build on. It imports no pytest (the library declares none, and the
`evals` facade is imported at run time) and its cases are sync methods calling `asyncio.run`.

Plan 007's Track D fills this.
"""

from __future__ import annotations

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.domain.declaration import VoiceAgent


class ActionSafetySuite:
    """A team's action, tested: a subclass gives the agent with a fresh backend and the action
    it tests, and inherits every case."""

    def make_agent(self) -> VoiceAgent:
        """A fresh agent, with its backend and its action (a backend is reached by a closure)."""
        raise NotImplementedError("plan 007's Track D fills ActionSafetySuite")

    def action_under_test(self) -> Action:
        """The action the suite tests."""
        raise NotImplementedError("plan 007's Track D fills ActionSafetySuite")
