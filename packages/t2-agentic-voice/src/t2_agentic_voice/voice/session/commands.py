"""The session's commands: what one call's session asks of voice's Pipecat modules, each carried
out in order by `Commands.run`. io.py says how the two sides meet; the
events are session_events.py's. Frozen dataclasses with no Pipecat type, and no time: the
Pipecat side stamps when each reached it, on the call's clock, where it needs one (the
file-fed transport's `FedCall`).

The agent speaks in replies the session numbers from 0 (io.py's replies), each clause keyed on
its reply and its index there, never on the caller's turn: a reply that answers a turn names it
too.
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.events import EndReason, TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId, SessionMessage


@dataclass(frozen=True, kw_only=True)
class ListenIn:
    """The language the speech-to-text bridge names to the provider for every turn from now on:
    the call's `Language`'s `primary` code (`ar`, `en`) under `stt.live_language = "session"`,
    or None under `auto`, when the provider detects it; under `detected`, the code the call
    moved to on a spoken switch request too (language_moves.py). Until the first, none is
    named."""

    language: str | None


@dataclass(frozen=True, kw_only=True)
class HearOverlap:
    """The caller's turn `turn_id` is an overlap: its speech began while a reply played, or within
    `DROP_AFTER_S` after one (playback.py; io.py's overlaps). Besides the turn's own transcript, the
    speech-to-text bridge sends the overlap's two parts, each reported with its `part`: its
    `window`, the first `window_ms` of it counted from `OVERLAP_LEAD_S` (voice/stt_bridge.py) before
    the speech detector heard its speech begin, if the speech still goes on then; and the `overlap`,
    all of its speech, once the detector hears it stop, never waiting for the turn's end. A
    `HearOverlap` that reaches the bridge after the detector heard the turn's speech stop gets its
    `overlap` sent at once, with no window. At most these two requests decide an overlap: the turn's
    own `Transcribed` reuses the overlap's transcript, with no request of its own, when no speech
    followed it. Once the overlap is decided, whatever the verdict, the session sends one `unduck`,
    right after `StopSpeaking` on a stop or a repeat (io.py's overlaps)."""

    turn_id: TurnId
    window_ms: int


@dataclass(frozen=True, kw_only=True)
class Speak:
    """Say one clause of a reply in the voice of `language`: clause `clause` of reply
    `reply_id`, which answers the caller's turn `turn_id` (None for one that answers none:
    io.py's replies); `text`, at most the provider's `max_chars`, in one text-to-speech request,
    sent as it is (the session made it the provider's text: call.py); or, for a fixed phrase,
    `audio` from the phrase cache, played with no request (`text`, the whole phrase as written
    whatever its length, kept for its caption and its span: one clause). Clauses play in the
    order they were asked for."""

    reply_id: ReplyId
    clause: ClauseIndex
    turn_id: TurnId | None
    text: str
    language: LanguageTag
    audio: AudioChunk | None = None


@dataclass(frozen=True, kw_only=True)
class StopSpeaking:
    """Drop the agent's speech at once: every clause the session has asked for so far, queued or
    playing, whatever its reply (io.py's stop path); `reply_id` names the session's newest
    reply. No audio frame of them reaches the output transport after it, and no event of a
    dropped clause follows: the session counts each reply it drops as done, waiting for no
    event of it, and hangs up at once if one was the `ended` notice."""

    reply_id: ReplyId


@dataclass(frozen=True, kw_only=True)
class Send:
    """Send the client `message` at once, ahead of any queued audio: an urgent transport message,
    which a stop never drops (item 8). The agent's voice is lowered and brought back this way,
    with `duck` and `unduck` (io.py's overlaps)."""

    message: SessionMessage


@dataclass(frozen=True, kw_only=True)
class HangUp:
    """End the call, for `reason`, whatever ended it (the caller's `hangup`, a limit, an error,
    or an `Ending` or a `TransportFailure` it was handed): the session's last command, after its
    `ended` message. The Pipecat side drops a turn's held audio and every clause's queued
    audio, sends no request and cancels any in flight, so a turn still open, or closed with its
    transcript still to come, gets no `TurnClosed` or `Transcribed` and stays unfinished in the
    report; it closes the peer, the close bounded by a timeout (item 20), and ends the
    pipeline. Only the report of a request that went before it may follow, then the call's
    stream ends (io.py's end)."""

    reason: EndReason


Command = ListenIn | HearOverlap | Speak | StopSpeaking | Send | HangUp
COMMANDS: tuple[type[Command], ...] = (ListenIn, HearOverlap, Speak, StopSpeaking, Send, HangUp)
