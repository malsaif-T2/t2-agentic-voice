"""The session's I/O: how one call's session (`voice/session/`, which imports no Pipecat:
ARCH-BAN) and voice's Pipecat modules meet, so each side builds against these modules alone
(plan 003, step 10; Track D builds the session, Track E the Pipecat side). This module holds the
protocols each side meets, the call's clock and what a session starts with; the events are
session_events.py's, the commands commands.py's.

The Pipecat side (the transport, the speech detector and the turn analyzer, the speech bridges,
the session bridge) tells the session what happened: each `SessionEvent` goes to
`Session.handle`, one at a time, in the order it happened. The session answers with `Command`s,
which the Pipecat side carries out in order (`Commands.run`). Neither holds a Pipecat type. The
items cited are plan 003's appendix, "Changes to the plan's interfaces".

- **Times.** Every event carries `at`, when it happened, in seconds on the call's `Clock`
  (`time.perf_counter` in a call, a fake clock in a test): the processors' own stamps, never
  Pipecat's `timestamp` fields, which step at 15.625 ms on Windows (item 6). The session reads
  the same clock, for its timers too.
- **Turns** are the caller's, keyed on the frames, never on `UserTurnProcessor`'s events, which
  run on tasks of their own, unordered against the frames (item 6): the speech-to-text bridge
  numbers each turn from 0 when its `UserStartedSpeakingFrame` reaches it, and stamps the number
  on the turn's end and its transcript, since the next turn's start can reach the session before
  the last turn's transcript. Each `TurnOpened` is followed by one `TurnClosed` and exactly one
  `Transcribed` of its `turn` part, in either order, an empty, failed or unusable result
  included (item 4), the `Transcribed` after the turn's `Transcribing` when a request went,
  unless the call ends first (the end, below); an overlap's turn has besides at most one
  `Transcribed` of each of its `window` and `overlap` parts (overlaps, below).
- **Replies** are the agent's, numbered by the session from 0: the greeting, said once
  connected, is reply 0, and each echo and each spoken notice the next. The session speaks a
  reply clause by clause (`Speak`), each clause keyed on its reply and its index there, and
  naming the caller's turn the reply answers (none for the greeting or a notice), so a turn
  and a reply never share a key. Each clause is within the provider's `max_chars`, so the
  text-to-speech bridge's TOKEN aggregation sends one request per clause (item 9), handing its
  `Synthesizing` as it goes; a fixed phrase (the greeting, the frame, a notice) is one clause
  whatever its length, played from the phrase cache with no request. Each reports `ClauseQueued`
  when its first audio is queued for the output, then `ClausePlayed` or `ClauseFailed`, unless
  a `StopSpeaking` drops it first or the call ends first (the end, below). A clause whose audio
  is empty (`turn_ends`' silent phrases) reports `ClauseQueued`, then `ClausePlayed`, never
  `ClauseFailed`, at its place in the output, sending no frame and opening no text-to-speech
  context, since Pipecat 1.15.0 reports a context that ends with no audio as an error.
- **The drop rule** (plan 003's decision log). A turn whose speech began (`speech_at`) while any
  reply played, the greeting included, or within 300 ms after a reply's last clause played, is
  not answered, so the agent never answers its own voice leaking past the browser's echo
  cancellation. The turn is still closed and transcribed, and kept on the timeline. It is the
  rule under `interruptions.mode = "drop"`, the half-duplex call plan 003 built, which gives
  no `HearOverlap`.
- **Overlaps** (plan 005). Under `interruptions.mode = "two_step"`, the default (the owner's
  ruling of 2026-11-06), such a turn is an overlap instead: the session sends `duck` at once
  (`Send`) and gives `HearOverlap`, and the
  speech-to-text bridge sends the overlap's `window` and `overlap` parts as that command says,
  each a `Transcribing` and a `Transcribed` naming its part; a `HearOverlap` that reaches the
  bridge after the detector heard the turn's speech stop gets its `overlap` part sent at once,
  with no window; one that reaches it after the turn closed gives the turn's own `Transcribed`,
  then an `overlap` part reusing it, with no `Transcribing` of its own. The session's rule
  judges each transcript as it comes: a stop (new words included) or a repeat gives
  `StopSpeaking` (and cancels the reply's work), then `unduck` right after it; anything else
  `unduck` once the overlap's own transcript has come, the turn not answered. So every `duck`
  ends with exactly one `unduck` once its overlap is decided, whatever the verdict, and no
  reply after it plays lowered; an overlap the call's end cuts gets none, since the client
  restores the volume when the call ends.
- **The stop path** (item 7). `StopSpeaking` drops the agent's speech at once: the session
  bridge, upstream of the text-to-speech bridge, calls `broadcast_interruption()`, and every
  processor drops its queued frames up to the output transport, so a stop drops every clause
  the session has asked for so far, whatever its reply, and the session names its newest reply
  in it. Up to about 40 ms already in the WebRTC track still plays, so "no audio frame of that
  reply is sent after a stop" holds at the output transport. No event of a dropped clause
  follows, one the Pipecat side held for the session included: the session counts each reply
  the stop dropped as done, waiting for no event of it, and if one was the `ended` notice it
  gives `HangUp` at once. Pipecat's own interruptions stay off: only the session stops speech.
- **Taps** (item 15). `CallerAudio` is the caller's audio as the pipeline hears it, taken after
  the transport, and `AgentAudio` the agent's as the output transport sends it: what the call's
  recorder writes, and only when the setting and a signed consent both allow it (invariant 8).
  The taps always flow; the recorder decides.
- **Messages.** The client's messages reach the session parsed (`FromClient`, from
  voice/protocol.py's object path: Pipecat parsed each message's text before handing it on,
  with no bound of ours), and the session's go out as `Send`, an urgent transport message a
  stop never drops (item 8).
- **Failures** (item 12). A connection that fails, or is not connected within voice's own
  deadline from offer to connected, is a `TransportFailure`: ICE failure pushes no error frame,
  so it comes from the connection's events. A provider's failure comes on the turn's or the
  clause's own event. The session emits the public `TransportFailed` and `ProviderFailed` of
  what it is handed, in its order, and the Pipecat side only logs those failures: it emits
  only the `ProviderFailed` of a speech bridge's error frame, which reaches no session event
  (voice/pipecat_events.py), so each failure reaches the observers once.
- **Usage.** The session counts each request from its report, handed as the request goes,
  whatever comes of it: a `Transcribing` is one speech-to-text request, its `audio_s` sent, and
  billed as Groq bills Whisper, at least 10 s a request (the design's 10.4); a `Synthesizing` is
  one text-to-speech request, its `Speak`'s text the characters sent. A request the call's end
  cancels is counted, never one that did not go; a phrase played from the cache is a cache hit.
- **The end.** The call ends at the first of an `Ending` or a `TransportFailure` the Pipecat
  side hands, or a `HangUp` the session gives, whatever ended it: the caller's `hangup` or their
  side closing, a limit, an error, the runtime stopping, the connection failing. From then the
  Pipecat side starts nothing and finishes nothing: it drops the held audio of a turn still
  open, or closed with its transcript still to come, and sends no request for it; drops every
  clause's audio still queued; and cancels any request in flight, speech-to-text's or
  text-to-speech's. It hands no event after the end, the taps included, but the report of a
  request that went before the end (its `Transcribing` or `Synthesizing`, which the session
  still reads and counts): so no `TurnClosed` or `Transcribed` of such a turn follows, and no
  `ClausePlayed` or `ClauseFailed` of such a clause. The session keeps the turn in the report
  as unfinished (`TurnRecord.unfinished`) and counts each reply the end cut as done, as a stop's
  (`AgentSpeechEnded` with how much of it played). The session's last command is always
  `HangUp`, given at once when an `Ending` or a `TransportFailure` ends the call; no command
  follows it. Once it has handed the last of those reports, the Pipecat side ends the call's
  stream with `Session.aclose`, and no event follows.

What else a session needs (the agent and the call's language, the settings, the phrase cache,
tracing, where its public events go) comes in its `CallSetup`, from voice's entry point
(`voice/calls.py`).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallId, Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.session.commands import Command
from t2_agentic_voice.voice.session.session_events import SessionEvent

# Where the session's public events go (core/events.py): the runtime's observers, queued off the
# call's path (the design's 6.6). It returns at once and never raises.
EventSink = Callable[[Event], None]


class Clock(Protocol):
    """A call's time: `now`, on the scale every event's `at` is on; `wall`, the time of day the
    public events and the report carry; and `sleep`, for the session's timers."""

    def now(self) -> float:
        """Seconds on a monotonic scale with no fixed start."""

    def wall(self) -> datetime:
        """The time of day now, aware (UTC)."""

    async def sleep(self, seconds: float) -> None:
        """Return once `seconds` have passed on this clock."""


class SystemClock:
    """The clock of a real call: `time.perf_counter`, whose resolution is far finer than
    `time.monotonic`'s 15.6 ms on Windows (plan 003's decision log), the system's UTC time, and
    asyncio's sleep."""

    def now(self) -> float:
        return time.perf_counter()

    def wall(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


SYSTEM_CLOCK = SystemClock()


class PhraseAudio(Protocol):
    """The audio of the runtime's fixed phrases (the greetings, the echo's frames, the notices),
    each synthesized once at the runtime's start and kept: what the session plays them from
    (adapters/phrase_cache.py's `PhraseCache` meets it)."""

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        """A declared phrase's audio in `language`'s voice, from memory, with no request.
        LookupError for any text not declared at the start: no heard words reach the cache
        (invariant 8)."""


class Session(Protocol):
    """One call's session as the Pipecat side drives it (voice/session/call.py's `CallSession`):
    each event of the call's stream through `handle`, then `aclose`, once, when it ends."""

    async def handle(self, event: SessionEvent) -> None:
        """Take one event, in the order they happened, and return soon: what takes longer (a
        timer, a report written to disk) runs on the session's own tasks. Never raises."""

    async def aclose(self) -> None:
        """The call's stream has ended (the end, above): no event follows, and the session
        gives no command. Finish the call, its report counted from every event handed and
        written, and return once it is. Never raises."""


class Commands(Protocol):
    """Where the session's commands go: the Pipecat side, which carries each out (the session
    bridge)."""

    async def run(self, command: Command) -> None:
        """Carry out `command`, after every command before it. Never raises: what fails comes
        back as an event. It returns once the command is queued: it never waits on the
        pipeline, on playback or on the peer's close, and never calls the session's `handle` or
        `aclose`, since the session awaits `run` while it holds the lock those take (TD-068);
        what the command brings about comes back as events, handed later."""


@dataclass(frozen=True, kw_only=True)
class CallSetup:
    """What one call's session starts with, from voice's entry point: the call's ID; who is
    calling and what they consented to, as the identity source verified them at join; the agent,
    and the call's language, one of the agent's, fixed at join (`VoiceAgent.call_language`) and
    kept for the whole call; the settings; the runtime's phrase audio; the most characters
    one text-to-speech request of a language takes (the provider's `max_chars`, which the clause
    splitter honours); the runtime's tracing; where the session's public events go; and the
    call's clock."""

    call_id: CallId
    caller: Caller
    consent: Consent
    agent: VoiceAgent
    language: Language
    settings: VoiceSettings
    phrases: PhraseAudio
    max_chars: Callable[[str], int | None]
    tracing: Tracing
    emit: EventSink
    clock: Clock = SYSTEM_CLOCK
