"""The moments a `TextCall` waits for before the caller says a turn (testing/text_call.py; plans
006 and 007), each read from the call as it now stands (testing/text_reads.py): the agent
silent, a reply playing, a tool of a reply running, a turn's reply written, and a read-back's
summary or its closing question playing (testing/text_read_back.py).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from t2_agentic_voice.agent.talker import ToolBegan, ToolEnded
from t2_agentic_voice.testing.text_read_back import Part, playing
from t2_agentic_voice.testing.text_reads import TextReads
from t2_agentic_voice.testing.text_watch import plans_of
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S

# When a turn is said: over the reply playing, or over a read-back's summary or its closing
# question.
During = Literal["agent_speaking", "read_back", "closing_question"]
# Where in a reply a turn is said: while one of its tools runs.
At = Literal["tool_running"]


def moment(
    reads: TextReads, during: During | None, at: At | None, *, now: Callable[[], float]
) -> tuple[Callable[[], bool], str]:
    """When a turn said `during` or `at` begins (silent, by default, on the clock `now` reads),
    and what a wait for it says when it never comes."""
    if at == "tool_running":
        return (lambda: tool_running(reads)), "no tool of a reply ran"
    if during == "agent_speaking":
        return (lambda: reads.session.playback.speaking), "no reply played"
    if during == "read_back":
        return (lambda: reading(reads, "summary")), "no read-back's summary played"
    if during == "closing_question":
        return (lambda: reading(reads, "question")), "no read-back's closing question played"
    return (lambda: silent(reads, now())), "the agent was never silent"


def silent(reads: TextReads, now: float) -> bool:
    """Whether the agent is silent at `now`: no reply in progress, and the last past its
    tail."""
    playback = reads.session.playback
    if playback.in_progress():
        return False
    ended = [r.ended_at for r in (playback.reply(i) for i in range(playback.next_id)) if r]
    last = max((at for at in ended if at is not None), default=None)
    return last is None or now > last + DROP_AFTER_S


def tool_running(reads: TextReads) -> bool:
    """Whether a tool of a reply still in progress runs now."""
    if reads.watched is None:
        return False
    for talk in reads.watched.talks.values():
        ended = {e.call_id for _, e in talk.events if isinstance(e, ToolEnded)}
        began = [e for _, e in talk.events if isinstance(e, ToolBegan)]
        if not talk.cancelled and any(e.call_id not in ended for e in began):
            return True
    return False


def written(reads: TextReads, turn_id: int) -> bool:
    """Whether the turn's reply is written whole, stopped, or none answers it."""
    session = reads.session
    fate = next((t.fate for t in session.history.turns() if t.turn_id == turn_id), "pending")
    replies = [r for r in session.history.replies() if r.turn_id == turn_id]
    if fate != "pending" or not replies:
        return fate != "pending" or reads.watched is None
    reply = session.playback.reply(replies[-1].reply_id)
    return reply is None or not reply.open or reply.ended_at is not None


def reading(reads: TextReads, part: Part) -> bool:
    """Whether a read-back's `part`, its summary or its closing question, plays now."""
    return playing(reads.session.playback, plans_of(reads.watched)) == part
