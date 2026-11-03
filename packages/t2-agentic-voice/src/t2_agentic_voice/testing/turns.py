"""Where a call's turns end, measured on the file-fed pipeline: `turn_ends`, which `poe eot` runs
over the golden set's paused requests (plan 003's registration, E), provisional, re-exported by
the `evals` facade since an app imports only public modules (plan 003's decision log). Built by
plan 003's Track H, which settles its fields; until then a stub.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

_STUB = "turn_ends is built by plan 003's Track H"


class TurnEnd(BaseModel):
    """One turn's end in a file-fed call, in milliseconds from the clip's start (the silence fed
    before it left out): when the speech detector last heard the speech stop before it, and when
    the turn analyzer ended the turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    speech_stop_ms: float
    end_ms: float


def turn_ends(
    clips: Iterable[AudioClip], *, settings: VoiceSettings, lead_s: float, tail_s: float
) -> AsyncIterator[tuple[TurnEnd, ...]]:
    """Each clip's turn ends, clip by clip: each clip fed as a fresh call through the file-fed
    pipeline at real-time pace, with `settings`' turn settings, `lead_s` of digital silence
    before it and `tail_s` after it, and a speech-to-text that answers at once, so the
    transcript adds no time; the models loaded once for every clip. No request leaves the
    machine, so the call plays no greeting: its agent, its text-to-speech and its phrase audio
    are testing's own, which say every text as silence of no length, so the greeting has played
    once the call is connected, and each clip's lead starts there (voice/file_transport.py's
    rule, unchanged). A greeting would move no turn end, which the speech detector and the turn
    analyzer find in the caller's audio alone, never in a file-fed call's captured output;
    taking the phrase cache's audio, as `echo_timings` does, would make `poe eot`, an offline run
    with no spend, synthesize the greeting (plan 003's registration, E). Track H's test: no
    call's output holds an audio frame of its greeting, and each clip's first frame is due
    `lead_s` after its greeting's `ClausePlayed`."""
    raise NotImplementedError(_STUB)
