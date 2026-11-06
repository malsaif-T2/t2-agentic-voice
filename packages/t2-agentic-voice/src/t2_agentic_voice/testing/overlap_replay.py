"""What came of one clip replayed over a reply (testing/audio_call.py's `AudioCall`, the design's
9.5, provisional): `OverlapReplay` and its requests, and `replay_of`, which reads them from the
replayed call alone, as the file-fed transport returned it (voice/file_transport.py's `FedCall`)
with the call's `Interrupted` events.

- **The verdict**: the first `Interrupted` that stopped the agent, else the first (a `false`
  kind is the reply going on), its kind and its `reason`, the rule's step; a `repeat_word` is a
  repeat.
- **When it was decided**: the session's first `StopSpeaking` for a stop, or, for a reply that
  went on, its first `unduck`.
- **The part that decided it**: the last `Transcribed` of an overlap's turn (one a `HearOverlap`
  named) handed to the session before then: a `window` or an `overlap` part, or the turn's own
  when the session judged it after a go on. Each event's handing time is `FedCall.handed_at`,
  so a transcript that came while the session was deciding is not taken for the one that
  decided (a call made by hand, with none, is read by its events' own times).
- **The overlaps**: the turns a `HearOverlap` named, in the order they were named; a long clip
  can open several, each decided by its own window and overlap parts, so each request carries
  its turn, and the turn whose transcript decided is named.
- **The requests**: each `Transcribing` of the call with its answer, the `Transcribed` of the
  same turn and part.
- **The speech's stop**: when the speech detector last heard the deciding turn's speech stop (its
  `TurnClosed`), or the first overlap's turn's when no transcript decided.
- **The last agent audio frame**, for a stop: the last `AgentAudio` the output sent before the
  next reply's first audio was queued (an echo's or a repeat's), and from the labelled word end
  to it (`stop_ms`).

Every time is in milliseconds from the clip's first frame, on the call's clock,
`time.perf_counter`, as testing/turns.py and testing/echo_timing.py time theirs (plan 003's
Track H).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import Interrupted, InterruptionKind, TurnId
from t2_agentic_voice.domain.interruptions import OverlapAction, VerdictReason
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import HearOverlap, Send, StopSpeaking
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseQueued,
    Transcribed,
    Transcribing,
    TurnClosed,
)

if TYPE_CHECKING:  # named in annotations only: this module imports no Pipecat
    from t2_agentic_voice.voice.file_transport import FedCall

# Which of a turn's speech-to-text requests one was (voice/session/session_events.py's
# `TranscriptPart`, spelt out for the public signature).
RequestPart = Literal["window", "overlap", "turn", "held"]


class OverlapRequest(BaseModel):
    """One speech-to-text request of the clip's call, in milliseconds from the clip's start: its
    turn and part, when it went and when its answer came (None when none did), the seconds of
    audio sent, the text heard, the provider's probability that it held no speech, and the
    failure it met, as `ProviderError` names it (None when it was answered)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn_id: TurnId
    part: RequestPart
    sent_ms: float
    answered_ms: float | None = None
    audio_s: float
    text: str | None = None
    no_speech_prob: float | None = None
    failure: ProviderErrorKind | None = None


class OverlapReplay(BaseModel):
    """One clip played over a reply: whether its speech opened an overlap, and the turns a
    `HearOverlap` named (`overlap_turns`); the verdict that decided it (its action, the
    `Interrupted` kind, the rule's step) and the part and turn whose transcript decided it, each
    None when none did; every speech-to-text request of its call; and, in milliseconds from the
    clip's start, when the speech detector last heard its speech stop, when the last agent audio
    frame was sent, and from the labelled word end to that last frame (`stop_ms`, None with no
    label or no stop)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opened: bool
    overlap_turns: tuple[TurnId, ...] = ()
    action: OverlapAction | None = None
    kind: InterruptionKind | None = None
    reason: VerdictReason | None = None
    decided_by: RequestPart | None = None
    decided_turn: TurnId | None = None
    requests: tuple[OverlapRequest, ...] = ()
    speech_stop_ms: float | None = None
    last_audio_ms: float | None = None
    stop_ms: float | None = None


def replay_of(
    fed: FedCall, interrupted: Sequence[Interrupted], *, word_end_ms: float | None = None
) -> OverlapReplay:
    """What came of one replayed call, as the module's docstring reads it: `fed`, as the
    file-fed transport returned it, `interrupted`, the call's `Interrupted` events in the order
    they came, and `word_end_ms`, the clip's labelled word end, which times the stop."""
    start = fed.started_at

    def ms(at: float) -> float:
        return (at - start) * 1000

    named = (c.turn_id for _, c in fed.commands if isinstance(c, HearOverlap))
    overlaps = tuple(dict.fromkeys(named))
    stops = [at for at, c in fed.commands if isinstance(c, StopSpeaking)]
    unducks = [
        at for at, c in fed.commands if isinstance(c, Send) and isinstance(c.message, Unduck)
    ]
    stopping = next((event for event in interrupted if event.kind != "false"), None)
    verdict = stopping or next(iter(interrupted), None)
    decided_at = next(iter(stops if stopping is not None and stops else unducks), None)
    handed = fed.handed_at or tuple(event.at for event in fed.events)
    deciding = [
        event
        for event, at in zip(fed.events, handed, strict=True)
        if isinstance(event, Transcribed)
        and event.turn_id in overlaps
        and decided_at is not None
        and at <= decided_at
    ]
    decider = deciding[-1] if deciding else None
    turn = decider.turn_id if decider is not None else min(overlaps, default=None)
    closed = next((e for e in fed.events if isinstance(e, TurnClosed) and e.turn_id == turn), None)
    last_audio = None
    if stopping is not None and stops:
        after = [e.at for e in fed.events if isinstance(e, ClauseQueued) and e.at > stops[0]]
        later = min(after, default=float("inf"))
        frames = [e.at for e in fed.events if isinstance(e, AgentAudio) and e.pcm16]
        last_audio = max((at for at in frames if at < later), default=None)
    last_audio_ms = None if last_audio is None else ms(last_audio)
    action: OverlapAction | None = None
    if verdict is not None:
        action = "go_on" if verdict.kind == "false" else "stop"
        action = "repeat" if verdict.reason == "repeat_word" else action
    return OverlapReplay(
        opened=bool(overlaps),
        overlap_turns=overlaps,
        action=action,
        kind=None if verdict is None else verdict.kind,
        reason=None if verdict is None else verdict.reason,
        decided_by=None if decider is None else decider.part,
        decided_turn=None if decider is None else decider.turn_id,
        requests=_requests(fed, ms),
        speech_stop_ms=None if closed is None else ms(closed.speech_ended_at),
        last_audio_ms=last_audio_ms,
        stop_ms=(
            None if word_end_ms is None or last_audio_ms is None else last_audio_ms - word_end_ms
        ),
    )


def _requests(fed: FedCall, ms: Callable[[float], float]) -> tuple[OverlapRequest, ...]:
    """Each request of the call, its `Transcribing`, with its answer, the `Transcribed` of the
    same turn and part, in the order they went."""
    answers = {(e.turn_id, e.part): e for e in fed.events if isinstance(e, Transcribed)}
    found = []
    for sent in (e for e in fed.events if isinstance(e, Transcribing)):
        answer = answers.get((sent.turn_id, sent.part))
        transcript = None if answer is None else answer.transcript
        found.append(
            OverlapRequest(
                turn_id=sent.turn_id,
                part=sent.part,
                sent_ms=ms(sent.at),
                answered_ms=None if answer is None else ms(answer.at),
                audio_s=sent.audio_s,
                text=None if transcript is None else transcript.text,
                no_speech_prob=None if transcript is None else transcript.no_speech_prob,
                failure=None if answer is None else answer.failure,
            )
        )
    return tuple(found)
