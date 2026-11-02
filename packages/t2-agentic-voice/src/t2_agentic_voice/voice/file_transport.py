"""The file-fed transport: one call whose caller is a clip of audio instead of a browser, through
the same voice modules as a call over WebRTC (the speech detector, the turn analyzer, the speech
bridges, the session bridge and the session), its output captured, never sent. Internal, for the
tests, `poe eot` and runs T1 and T2, which reach it through testing's `turn_ends` and
`echo_timings` (plan 003's decision log); the public `AudioCall` and its parity test come later
(the design's 9.5). Built by plan 003's Track E; until then a stub.

The clip is fed at real-time pace, so Pipecat's timers run as in a call: 20 ms frames, each due
at an absolute deadline on `time.perf_counter` (the call's start plus n frames), since relative
sleeps drift and asyncio's clock steps at about 15.6 ms on Windows under Python 3.12. The spike
held 60 s within the 100 ms tolerance on one `asyncio.sleep` a frame (its end 4.9 ms early), but
sent frames up to 30 ms early and 19 ms late at the 99th percentile; a hybrid pacer was exact, at
about 43% of a core. Smart Turn stalls audio 100 to 163 ms at each speech stop, which the
timings must allow for (plan 003's appendix, "Changes to the plan's interfaces", item 23).
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.session.io import Command, SessionEvent

_STUB = "the file-fed transport is built by plan 003's Track E"


@dataclass(frozen=True, kw_only=True)
class FedCall:
    """What one file-fed call did: when the clip's first frame was due (`started_at`, on the
    call's clock; the silence before the clip comes first), every event the Pipecat side handed
    the session, and every command the session gave, each in its order, with their times."""

    started_at: float
    events: tuple[SessionEvent, ...]
    commands: tuple[Command, ...]


async def feed_file(
    calls: VoiceCalls,
    clip: AudioClip,
    *,
    call_id: CallId,
    caller: Caller,
    consent: Consent,
    lead_s: float,
    tail_s: float,
) -> FedCall:
    """Run one call of `calls` (started: its models loaded once for every call fed) whose caller
    is `lead_s` of digital silence (zeros), then `clip` (mono PCM16 at the speech detector's
    16 kHz), then `tail_s` of silence, fed at real-time pace. After the last frame the caller
    leaves (an `Ending`, `caller_left`); what the call did is returned once its session has hung
    up. Every aiortc peer it may build gets no ICE server."""
    raise NotImplementedError(_STUB)
