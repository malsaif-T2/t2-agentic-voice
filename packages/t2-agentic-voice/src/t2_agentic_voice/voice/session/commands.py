"""The session's commands: what one call's session asks of voice's Pipecat modules, each carried
out in order by `Commands.run` (plan 003, step 10). io.py says how the two sides meet; the
events are session_events.py's. Frozen dataclasses with no Pipecat type, and no time: the
Pipecat side stamps when each reached it, on the call's clock, where it needs one (the
file-fed transport's `FedCall`).

The agent speaks in replies the session numbers from 0 (the greeting reply 0, each echo and each
spoken notice the next), each clause keyed on its reply and its index there, never on the
caller's turn: a reply that answers a turn names it too.
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
    or None under `auto`, when the provider detects it. Until the first, none is named."""

    language: str | None


@dataclass(frozen=True, kw_only=True)
class Speak:
    """Say one clause of a reply in the voice of `language`: clause `clause` of reply
    `reply_id`, which answers the caller's turn `turn_id` (None for the greeting or a spoken
    notice); `text`, at most the provider's `max_chars`, in one text-to-speech request; or, for a
    fixed phrase, `audio` from the phrase cache, played with no request (`text` kept for its
    caption and its span). Clauses play in the order they were asked for."""

    reply_id: ReplyId
    clause: ClauseIndex
    turn_id: TurnId | None
    text: str
    language: LanguageTag
    audio: AudioChunk | None = None


@dataclass(frozen=True, kw_only=True)
class StopSpeaking:
    """Drop the agent's speech at once, every clause queued or playing, of reply `reply_id` and
    of any before it (io.py's stop path): no audio frame of them reaches the output transport
    after it, and no event of a dropped clause follows."""

    reply_id: ReplyId


@dataclass(frozen=True, kw_only=True)
class Send:
    """Send the client `message` at once, ahead of any queued audio: an urgent transport message,
    which a stop never drops (item 8)."""

    message: SessionMessage


@dataclass(frozen=True, kw_only=True)
class HangUp:
    """End the call, for `reason`: the session's last command, after its `ended` message. The
    Pipecat side closes the peer, the close bounded by a timeout (item 20), and ends the
    pipeline; no event follows."""

    reason: EndReason


Command = ListenIn | Speak | StopSpeaking | Send | HangUp
COMMANDS: tuple[type[Command], ...] = (ListenIn, Speak, StopSpeaking, Send, HangUp)
