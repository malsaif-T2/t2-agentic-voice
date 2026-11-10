"""The stubs plan 007's Block 0 left for Track B, each raising with the track's name. Track B
deletes this file as it fills them: the outboxes, the record and the action runner are filled
(test_outbox.py, test_record.py, test_action_*.py); `past_actions` is left for the talker's side."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.core.identity import Caller

TRACK = "Track B"
CONTEXT = CallContext(caller=Caller(subject="m"), call_id="c", language="en")


def test_past_actions_is_a_stub() -> None:
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(CONTEXT.past_actions("open_request"))
