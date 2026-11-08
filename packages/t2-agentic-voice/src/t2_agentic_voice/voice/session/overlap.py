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
the call ends). A rule that raises (a bug) decides the overlap at once as going on, logged by its
kind with no text, so its `unduck` follows and no later one waits on it. At most two requests
decide one overlap, its window's and its whole overlap's; once one stops the agent, the other's
verdict changes nothing, but after a stop or a repeat request its window heard: the whole overlap
is judged still (`asked_again`; its verdict says what follows the stop, interrupter.py's), since a
window may hold only a request's first word. The turn's own transcript decides only an overlap
whose whole-overlap request had not gone when it came (its `HearOverlap` reached the bridge after
the turn closed: the whole overlap then reuses the turn's result, and changes nothing), and is
judged again after a verdict to go on when speech followed it (`followed`, `judge_after`), at no
request. When the rule lets the transcript that decides go on for want of words, on two or more,
and the call's agent asks for it (domain/uncertain_overlaps.py, D-069), the overlap stays
undecided (`asking`) until a chat model's word (overlap_ask.py), so its `unduck` waits too.

The rule reads each transcript's speech time (`Overlap.speech_s`) from the turn's `speech_at`: a
window's to its request, the speech still going on; the whole overlap's to its request less the
speech detector's stop delay (`turns.vad_stop_ms`), since that request goes once the detector
hears the speech stop; and the turn's own to when its speech ended.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.interruptions import Overlap, Verdict, judge
from t2_agentic_voice.domain.silence import CAPTIONS
from t2_agentic_voice.domain.uncertain_overlaps import is_uncertain
from t2_agentic_voice.domain.words import WORD_KINDS, Words
from t2_agentic_voice.voice.protocol import Duck, ReplyId
from t2_agentic_voice.voice.session.commands import Command, HearOverlap, Send
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TranscriptPart,
)

_log = get_logger(__name__)
# The verdict on a transcript the rule failed on (a bug): the reply goes on, as for no words.
_FAILED = Verdict(action="go_on", kind="false", reason="no_words")


def answers(verdict: Verdict) -> bool:
    """Whether the turn behind `verdict` is answered: new words or a correction that stopped
    the agent; a stop or pause word, a repeat request or a verdict to go on is not."""
    return verdict.action == "stop" and verdict.kind in ("new_words", "correction")


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


@dataclass(frozen=True, kw_only=True)
class Asking:
    """The transcript a chat model is asked about (overlap_ask.py), and the rule's `verdict` on
    it, which stands unless the model says stop."""

    verdict: Verdict
    event: Transcribed


@dataclass(kw_only=True)
class OverlapState:
    """One overlap: the caller's turn, the reply it spoke over, when its speech began and when
    the agent's voice was lowered; the verdict on its window's transcript and on its whole
    overlap's, each None until it came; the one that `decided` it and which transcript that
    was (`decided_by`), None while it is open; the transcript a chat model is being asked about
    (`asking`), the overlap undecided until it answers; the transcripts asked for and come so
    far; and whether its `unduck` went."""

    turn_id: TurnId
    reply_id: ReplyId
    speech_at: float
    ducked_at: float
    window: Verdict | None = None
    overlap: Verdict | None = None
    decided: Verdict | None = None
    decided_by: TranscriptPart | None = None
    asking: Asking | None = None
    asked: set[TranscriptPart] = field(default_factory=set)
    heard: set[TranscriptPart] = field(default_factory=set)
    unducked: bool = False

    @property
    def waiting(self) -> bool:
        """Whether its whole overlap's request went and its transcript has not come."""
        return "overlap" in self.asked and "overlap" not in self.heard

    @property
    def asked_again(self) -> bool:
        """Whether its window's stop or repeat request decided it: its whole overlap's
        transcript is judged still (`overlap`), to say what follows the stop."""
        decided = self.decided
        return decided is not None and decided.action != "go_on" and self.decided_by == "window"

    @property
    def followed(self) -> bool:
        """Whether speech followed the transcript that decided it, in the same turn: the turn's
        own request went, and the transcript that decided was a part with a request of its own,
        not the turn's result reused."""
        decided_by = self.decided_by
        asked = self.asked
        return "turn" in asked and decided_by not in (None, "turn") and decided_by in asked

    @property
    def reads_on(self) -> bool:
        """Whether its turn's own transcript is read for what followed the stop word or the
        repeat request that decided it (interrupter.py's what followed): speech followed that
        transcript, and nothing it or the whole overlap holds is answered."""
        decided = self.decided
        stopped = decided is not None and decided.action != "go_on" and not answers(decided)
        return stopped and self.followed and not self.instead

    @property
    def instead(self) -> bool:
        """Whether its turn is answered after its window's stop word, or instead of its window's
        repeat request: its whole overlap holds new words or a correction."""
        return self.asked_again and self.overlap is not None and answers(self.overlap)

    @property
    def awaits(self) -> bool:
        """Whether its turn's own transcript waits: for its whole overlap's (`waiting`), which
        says what the turn's does (it is undecided, or its window's stop or repeat request asks
        what follows); or for a chat model's word on a transcript of it."""
        decided = self.decided
        waits = self.waiting and (decided is None or (self.asked_again and not answers(decided)))
        return waits or self.asking is not None

    def settled(self, verdict: Verdict) -> None:
        """The chat model's word, or the rule's when it gave none, decides the overlap."""
        if self.asking is not None:
            self.decided, self.decided_by = verdict, self.asking.event.part
        self.asking = None


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
        self._asks_model = (
            setup.agent.ask_on_uncertain_overlaps
            and setup.talker is not None
            and setup.overlap_model is not None
        )
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
        already (its whole overlap's after its window's stop or repeat request is judged still,
        and decides nothing), or a chat model is being asked about it, or the transcript is not
        an overlap's. A window's verdict to go on leaves the overlap open, unless the rule failed
        on it; any other verdict decides it, but a verdict to go on for want of words on two or
        more words, when the agent asks for it, leaves it undecided for the model's word."""
        state = self._overlaps.get(event.turn_id)
        if state is None:
            return None
        state.heard.add(event.part)
        if state.decided is not None and not (state.asked_again and event.part == "overlap"):
            return None
        if state.asking is not None:
            return None
        verdict, failed = self._verdict(state, event, played, ended_at)
        if event.part == "window":
            state.window = verdict
        else:
            state.overlap = verdict
        opens = event.part == "window" and verdict.action == "go_on" and not failed
        if state.decided is None and not opens:
            if self._uncertain(verdict, event):
                state.asking = Asking(verdict=verdict, event=event)
            else:
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
        return self._verdict(state, event, played, ended_at)[0] if state.followed else None

    def settle(self) -> int:
        """How many `unduck`s go now: one for each overlap decided whose `unduck` has not
        gone, once no overlap of the call is undecided; none while one is."""
        if self.open_turns:
            return 0
        due = [state for state in self._overlaps.values() if not state.unducked]
        for state in due:
            state.unducked = True
        return len(due)

    @property
    def words(self) -> Words:
        """The words the call's rule reads (`call_words`)."""
        return self._words

    def get(self, turn_id: TurnId) -> OverlapState | None:
        """The overlap of the caller's turn `turn_id`; None when it is none."""
        return self._overlaps.get(turn_id)

    @property
    def open_turns(self) -> tuple[TurnId, ...]:
        """The overlaps not yet decided, by their turns, in order."""
        found = (state.turn_id for state in self._overlaps.values() if state.decided is None)
        return tuple(sorted(found))

    def _uncertain(self, verdict: Verdict, event: Transcribed) -> bool:
        """Whether a chat model decides the transcript the rule let go on for want of words
        (domain/uncertain_overlaps.py)."""
        text = "" if event.transcript is None else event.transcript.text
        return self._asks_model and is_uncertain(verdict, text, words=self._words)

    def _verdict(
        self,
        state: OverlapState,
        event: Transcribed,
        played: Sequence[str],
        ended_at: float | None,
    ) -> tuple[Verdict, bool]:
        """The rule's verdict on the transcript, and whether the rule failed on it: then going
        on (`_FAILED`), the failure logged by its kind alone."""
        try:
            return self._judged(state, event, played, ended_at), False
        except Exception as error:  # a bug: the reply goes on, so no overlap stays undecided
            _log.error(
                "overlap_judge_failed",
                call_id=self._setup.call_id,
                turn_id=state.turn_id,
                part=event.part,
                failure=type(error).__qualname__,
            )
            return _FAILED, True

    def _judged(
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
