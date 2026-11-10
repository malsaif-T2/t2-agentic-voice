"""The stub plan 007's Block 0 left for Track D. Track D deletes this file as it fills it."""

from __future__ import annotations

import pytest
from t2_agentic_voice.evals import ActionSafetySuite


def test_the_safety_suite_is_a_stub() -> None:
    suite = ActionSafetySuite()
    with pytest.raises(NotImplementedError, match="Track D"):
        suite.make_agent()
    with pytest.raises(NotImplementedError, match="Track D"):
        suite.action_under_test()
