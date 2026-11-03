"""The session's overlaps (io.py's overlaps; plan 005): under `interruptions.mode = "two_step"`,
a turn whose speech began while a reply played, or within 300 ms after one, is an overlap of that
reply. The session opens it at the turn's `TurnOpened` (`open`: `duck` at
`interruptions.duck_level`, then `HearOverlap` with `interruptions.first_window_ms`), judges each
of its transcripts with the rule as it comes (`judge`: domain/interruptions.py's `judge`, with the
call language's words, `call_words`, and the texts of the clauses that played within
`interruptions.own_words_s` and the one playing now), and keeps what decided it: a stop or a
repeat (`StopSpeaking`, then `unduck` right after it), or the reply going on (`unduck` once the
whole overlap's transcript has come, the turn not answered). A window's verdict decides only when
it stops the agent; the whole overlap's decides whatever it says. Every overlap's `duck` ends with
exactly one `unduck` once it is decided, whatever the verdict, but none while another overlap of
the call is still undecided (`settle`), so one decision never raises the agent's voice over speech
still being judged; an overlap the call's end cuts gets none (the client restores the volume when
the call ends). At most two requests decide one overlap, its window's and its whole overlap's;
once one stops the agent, the other's verdict changes nothing. The turn's own transcript decides
only an overlap whose whole-overlap request had not gone when it came (its `HearOverlap` reached
the bridge after the turn closed: the whole overlap then reuses the turn's result, and changes
nothing), and is judged again after a verdict to go on when speech followed it (`judge_after`),
at no request.

The rule reads each transcript's speech time (`Overlap.speech_s`) from the turn's `speech_at`: a
window's to its request, the speech still going on; the whole overlap's to its request less the
speech detector's stop delay (`turns.vad_stop_ms`), since that request goes once the detector
hears the speech stop; and the turn's own to when its speech ended.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.interruptions import Overlap, Verdict, judge
from t2_agentic_voice.domain.silence import CAPTIONS
from t2_agentic_voice.domain.words import WORD_KINDS, Words
from t2_agentic_voice.voice.protocol import Duck, ReplyId
from t2_agentic_voice.voice.session.commands import Command, HearOverlap, Send
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TranscriptPart,
)


def call_words(setup: CallSetup) -> Words:
    """The words a call's rule reads, for its language's primary code: the language preset's,
    the agent's `phrases` and the `words` settings group's additions, each kind in that order,
    none twice."""
    code = setup.language.primary
    sources = (setup.language.words, setup.agent.phrases.words(code))
    added = setup.settings.words
    lists: dict[str, tuple[str, ...]] = {}
    for kind in WORD_KINDS:
        found = [word for words in sources for word in getattr(words, kind)]
        found += getattr(added, kind).get(code, ())
        lists[kind] = tuple(dict.fromkeys(found))
    return Words.model_validate(lists)


@dataclass(kw_only=True)
class OverlapState:
    """One overlap: the caller's turn, the reply it spoke over, when its speech began and when
    the agent's voice was lowered; the verdict on its window's transcript and on its whole
    overlap's, each None until it came; the one that `decided` it and which transcript that
    was (`decided_by`), None while it is open; the transcripts asked for and come so far; and
    whether its `unduck` went."""

    turn_id: TurnId
    reply_id: ReplyId
    speech_at: float
    ducked_at: float
    window: Verdict | None = None
    overlap: Verdict | None = None
    decided: Verdict | None = None
    decided_by: TranscriptPart | None = None
    asked: set[TranscriptPart] = field(default_factory=set)
    heard: set[TranscriptPart] = field(default_factory=set)
    unducked: bool = False

    @property
    def waiting(self) -> bool:
        """Whether its whole overlap's request went and its transcript has not come."""
        return "overlap" in self.asked and "overlap" not in self.heard


class Overlaps:
    """One call's overlaps, by the caller's turn."""

    def __init__(self, setup: CallSetup) -> None:
        self._setup = setup
        settings = setup.settings
        self._rules = settings.interruptions
        self._stop_s = settings.turns.vad_stop_ms / 1000
        self._no_speech_max = settings.stt.no_speech_max
        self._captions = CAPTIONS if settings.stt.caption_filter else ()
        self._words = call_words(setup)
        self._overlaps: dict[TurnId, OverlapState] = {}

    def open(
        self, turn_id: TurnId, *, reply_id: ReplyId, speech_at: float, at: float
    ) -> list[Command]:
        """Mark the turn an overlap of reply `reply_id`, at `at`: the commands that begin it,
        `duck` (a `Send`) and `HearOverlap`, in that order."""
        self._overlaps[turn_id] = OverlapState(
            turn_id=turn_id, reply_id=reply_id, speech_at=speech_at, ducked_at=at
        )
        rules = self._rules
        return [
            Send(message=Duck(level=rules.duck_level)),
            HearOverlap(turn_id=turn_id, window_ms=rules.first_window_ms),
        ]

    def requested(self, event: Transcribing) -> None:
        """A transcript of an overlap's turn was asked for (its request went)."""
        state = self._overlaps.get(event.turn_id)
        if state is not None:
            state.asked.add(event.part)

    def judge(
        self, event: Transcribed, *, played: Sequence[str], ended_at: float | None = None
    ) -> Verdict | None:
        """The rule's verdict on an overlap's transcript (its `window` or its `overlap` part, or
        the turn's own when no whole overlap's request went), with `played`, the texts of the
        clauses that played within `own_words_s` and the one playing now, and for the turn's own
        transcript `ended_at`, when its speech ended; None when the overlap was decided
        already, or the transcript is not an overlap's. A window's verdict to go on leaves the
        overlap open; any other verdict decides it."""
        state = self._overlaps.get(event.turn_id)
        if state is None:
            return None
        state.heard.add(event.part)
        if state.decided is not None:
            return None
        verdict = self._verdict(state, event, played, ended_at)
        if event.part == "window":
            state.window = verdict
        else:
            state.overlap = verdict
        if verdict.action != "go_on" or event.part != "window":
            state.decided, state.decided_by = verdict, event.part
        return verdict

    def judge_after(
        self, event: Transcribed, *, played: Sequence[str], ended_at: float | None
    ) -> Verdict | None:
        """The rule's verdict on the turn's own transcript of an overlap the rule let go on,
        when speech followed the transcript that decided it (the turn's own request went, and
        the transcript that decided was not the same result reused): a word asking the agent to
        stop after a listening sound, in one turn, still stops it. None for any other turn."""
        state = self._overlaps.get(event.turn_id)
        if state is None or state.decided is None or state.decided.action != "go_on":
            return None
        decided_by = state.decided_by
        if "turn" not in state.asked or decided_by == "turn" or decided_by not in state.asked:
            return None
        return self._verdict(state, event, played, ended_at)

    def settle(self) -> int:
        """How many `unduck`s go now: one for each overlap decided whose `unduck` has not
        gone, once no overlap of the call is undecided; none while one is."""
        if self.open_turns:
            return 0
        due = [state for state in self._overlaps.values() if not state.unducked]
        for state in due:
            state.unducked = True
        return len(due)

    def get(self, turn_id: TurnId) -> OverlapState | None:
        """The overlap of the caller's turn `turn_id`; None when it is none."""
        return self._overlaps.get(turn_id)

    @property
    def open_turns(self) -> tuple[TurnId, ...]:
        """The overlaps not yet decided, by their turns, in order."""
        found = (state.turn_id for state in self._overlaps.values() if state.decided is None)
        return tuple(sorted(found))

    def _verdict(
        self,
        state: OverlapState,
        event: Transcribed,
        played: Sequence[str],
        ended_at: float | None,
    ) -> Verdict:
        transcript = event.transcript
        if ended_at is None:
            sent = event.at if event.sent_at is None else event.sent_at
            ended_at = sent if event.part == "window" else sent - self._stop_s
        overlap = Overlap(
            text="" if transcript is None else transcript.text,
            no_speech_prob=None if transcript is None else transcript.no_speech_prob,
            speech_s=max(0.0, ended_at - state.speech_at),
            played=tuple(played),
            language=self._setup.language.primary,
        )
        rules = self._rules
        return judge(
            overlap,
            words=self._words,
            no_speech_max=self._no_speech_max,
            captions=self._captions,
            min_words=rules.min_words,
            short_words=rules.short_words,
            short_s=rules.short_s,
        )
