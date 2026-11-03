"""The session's overlaps (io.py's overlaps; plan 005): under `interruptions.mode = "two_step"`,
a turn whose speech began while a reply played, or within 300 ms after one, is an overlap of that
reply. The session opens it at the turn's `TurnOpened` (`open`: `duck` at
`interruptions.duck_level`, then `HearOverlap` with `interruptions.first_window_ms`), judges each
of its transcripts with the rule as it comes (`judge`: domain/interruptions.py's `judge`, with the
call language's words, `call_words`, and the texts of the clauses played in the last
`interruptions.own_words_s`), and keeps what decided it: a stop, a repeat, or the reply going on
(`unduck`, the turn not answered). At most two requests decide one overlap, its window's and its
whole overlap's; once one stops the agent, the other's verdict changes nothing.

Plan 005's Track B builds it; until then each method but the constructor raises.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.words import Words
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.commands import Command
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.session_events import Transcribed


def call_words(setup: CallSetup) -> Words:
    """The words a call's rule reads, for its language's primary code: the agent's `phrases`
    with the `words` settings group's additions."""
    raise NotImplementedError("the session's overlaps are plan 005's Track B's to build")


@dataclass(kw_only=True)
class OverlapState:
    """One overlap: the caller's turn, the reply it spoke over, when its speech began and when
    the agent's voice was lowered; the verdict on its window's transcript and on its whole
    overlap's, each None until it came; and the one that `decided` it, None while it is open."""

    turn_id: TurnId
    reply_id: ReplyId
    speech_at: float
    ducked_at: float
    window: Verdict | None = None
    overlap: Verdict | None = None
    decided: Verdict | None = None


class Overlaps:
    """One call's overlaps, by the caller's turn."""

    def __init__(self, setup: CallSetup) -> None:
        self._setup = setup
        self._overlaps: dict[TurnId, OverlapState] = {}

    def open(
        self, turn_id: TurnId, *, reply_id: ReplyId, speech_at: float, at: float
    ) -> list[Command]:
        """Mark the turn an overlap of reply `reply_id`, at `at`: the commands that begin it,
        `duck` (a `Send`) and `HearOverlap`, in that order."""
        raise NotImplementedError("the session's overlaps are plan 005's Track B's to build")

    def judge(self, event: Transcribed, *, played: Sequence[str]) -> Verdict | None:
        """The rule's verdict on an overlap's transcript (its `window` or its `overlap` part),
        with `played`, the texts of the clauses played in the last `own_words_s`; None when the
        overlap was decided already, or the transcript is not an overlap's."""
        raise NotImplementedError("the session's overlaps are plan 005's Track B's to build")

    def get(self, turn_id: TurnId) -> OverlapState | None:
        """The overlap of the caller's turn `turn_id`; None when it is none."""
        raise NotImplementedError("the session's overlaps are plan 005's Track B's to build")

    @property
    def open_turns(self) -> tuple[TurnId, ...]:
        """The overlaps not yet decided, by their turns, in order."""
        raise NotImplementedError("the session's overlaps are plan 005's Track B's to build")
