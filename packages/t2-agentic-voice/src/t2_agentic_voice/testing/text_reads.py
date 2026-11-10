"""What a `TextCall`'s turns and checks are read from (testing/text_call.py; plans 006 and 007):
its session and its side, the caller's turns as the call said them, and what it watched of its
talker, its tools and the part that acts (testing/text_watch.py), so a turn's reads
(testing/text_turn.py), its action expectations (testing/text_actions.py) and the call's checks
(testing/text_checks.py) each read the call as it now stands.
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.testing.text_side import TextSide
from t2_agentic_voice.testing.text_watch import RecordingJobs, RecordingRunner, WatchedTalker
from t2_agentic_voice.voice.session.call import CallSession


@dataclass(frozen=True, kw_only=True)
class TurnSaid:
    """One of the caller's turns as the text call said it: its number, its text, when its
    words were handed to the session, when its speech began (`spoke_at`), and the number the
    session's next reply would take then (`first_reply`), so what the agent said from then on
    can be read."""

    turn_id: int
    text: str
    handed_at: float
    spoke_at: float = 0.0
    first_reply: int = 0


@dataclass(frozen=True, kw_only=True)
class TextReads:
    """What a text call's turns are read from: its session, its side, the turns said, what it
    watched of its talker and its tools (none for a call of the echo), and for an agent with
    actions, the part that acts as the session handed it each job (`jobs`) and the call's
    record of completed actions (`record`), None for an agent with none."""

    session: CallSession
    side: TextSide
    said: dict[int, TurnSaid]
    watched: WatchedTalker | None
    runner: RecordingRunner | None
    jobs: RecordingJobs | None = None
    record: ActionRecord | None = None
