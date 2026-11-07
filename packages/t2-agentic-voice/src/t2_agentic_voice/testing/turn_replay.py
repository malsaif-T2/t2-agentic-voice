"""What came of one clip replayed as a turn (testing/audio_call.py's `AudioCall.turn`; plan 006's
time to first audio): the clip said while the agent was silent, after its greeting, and answered
(by the agent's talker, or its echo). `turn_replay_of` reads it from the replayed call alone, as
the file-fed transport returned it (voice/file_transport.py's `FedCall`), with the call's public
events: the first turn's times as the session took them (its `TurnMetrics`), and the first
audible frame of the reply that answers it as the output sent it (voice/session/turn_book.py's
`audible`; a progress line's, a fixed phrase that names a tool's wait, apart), each in
milliseconds from the clip's first frame, and from the clip's labelled end of speech when given;
and the reply's opening, its first `OPENING_S` seconds of audio from its first frame sent, for a
listen of its first syllable.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.events import Event, TurnMetrics, TurnTimes
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
)
from t2_agentic_voice.voice.session.turn_book import audible

if TYPE_CHECKING:  # named in annotations only: this module imports no Pipecat
    from t2_agentic_voice.voice.file_transport import FedCall

# The most of a reply's audio its opening keeps, in seconds from its first frame sent.
OPENING_S = 3.0


class TurnReplay(BaseModel):
    """One clip replayed as a turn: the session's times of its first turn (`times`, None when
    no turn closed), the first audible frame of the reply answering it and of a progress line,
    from the clip's first frame (None when none was sent), and from the clip's labelled end of
    speech to each (`ttfa_ms`, `progress_ms`, None with no label); and the reply's `opening`,
    its audio as sent from its first frame, silent ones included, for at most `OPENING_S`
    seconds (None when it sent none), a progress line's never part of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    times: TurnTimes | None = None
    first_audible_ms: float | None = None
    progress_audible_ms: float | None = None
    ttfa_ms: float | None = None
    progress_ms: float | None = None
    opening: AudioChunk | None = None


def turn_replay_of(
    fed: FedCall,
    emitted: Sequence[Event],
    *,
    progress: frozenset[str] = frozenset(),
    speech_end_ms: float | None = None,
) -> TurnReplay:
    """What came of one clip replayed as a turn (the module's docstring); `progress` holds the
    texts of the agent's progress lines, and `speech_end_ms` the clip's labelled end of speech,
    from its first frame."""
    start = fed.started_at
    metrics = next((e for e in emitted if isinstance(e, TurnMetrics) and e.turn_id == 0), None)
    fields = set(TurnTimes.model_fields)
    times = None if metrics is None else TurnTimes(**metrics.model_dump(include=fields))
    speaks = {(c.reply_id, c.clause): c for _, c in fed.commands if isinstance(c, Speak)}
    answering = {key for key, speak in speaks.items() if speak.turn_id == 0}
    queued: deque[tuple[int, int]] = deque()  # the clauses queued, the one playing first
    first: dict[bool, float] = {}
    opening: list[AgentAudio] = []  # the reply's own frames, from its first, at one rate
    for event in fed.events:
        if isinstance(event, ClauseQueued):
            queued.append((event.reply_id, event.clause))
        elif isinstance(event, ClausePlayed | ClauseFailed):
            key = (event.reply_id, event.clause)
            if key in queued:
                queued.remove(key)
        elif isinstance(event, AgentAudio) and queued and queued[0] in answering:
            playing = speaks[queued[0]]
            kind = playing.audio is not None and playing.text in progress
            if kind not in first and audible(event.pcm16):
                first[kind] = (event.at - start) * 1000
            if not kind and _wanted(opening, event):
                opening.append(event)
    heard, waited = first.get(False), first.get(True)

    def since(at_ms: float | None) -> float | None:
        if at_ms is None or speech_end_ms is None:
            return None
        return max(0.0, at_ms - speech_end_ms)

    return TurnReplay(
        times=times,
        first_audible_ms=heard,
        progress_audible_ms=waited,
        ttfa_ms=since(heard),
        progress_ms=since(waited),
        opening=_opening(opening),
    )


def _wanted(frames: Sequence[AgentAudio], frame: AgentAudio) -> bool:
    """Whether the opening so far, `frames`, takes `frame`: at their rate, while under
    `OPENING_S` seconds."""
    if not frames:
        return True
    rate = frames[0].sample_rate
    held = sum(len(each.pcm16) for each in frames)
    return frame.sample_rate == rate and held < OPENING_S * rate * 2


def _opening(frames: Sequence[AgentAudio]) -> AudioChunk | None:
    """The first `OPENING_S` seconds of `frames`, joined; None for no audio."""
    if not frames:
        return None
    rate = frames[0].sample_rate
    pcm16 = b"".join(frame.pcm16 for frame in frames)[: round(OPENING_S * rate) * 2]
    return AudioChunk(pcm16=pcm16, sample_rate=rate) if pcm16 else None
